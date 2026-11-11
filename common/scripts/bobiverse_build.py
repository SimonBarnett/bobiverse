"""Repo-generic BUILD job (FR #4006 / #4025) + INSTALL-TEST (FR #4026 WP3).

WP1: load/validate .bobiverse/build.yml, classify failures, single-flight lock,
ops `!build` parse/decide, dry-run plans (no agent tokens).

WP2 (FR #4025): deterministic live runner (`BuildRunner`), FakeGitHubFiler,
`BUILD v1` consume/enqueue, pack/release only when no new blockers.

WP3 (FR #4026): optional `!installtest` --- msiexec pre-release MSIs + post-checks + blockers.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML may be absent in slim envs
    yaml = None  # type: ignore

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RELEASE_BLOCKER_LABEL = "release-blocker"
FEATURE_REQUEST_LABEL = "feature-request"
# FR #4316: guard/runner aborts are reproducible anywhere the suite runs — not ionos-only.
MACHINE_ANY_LABEL = "machine:any"


# ------------------------------------------------------------------ recipe


@dataclass
class SuiteSpec:
    name: str
    cmd: str
    cwd: str = "."
    env: dict = field(default_factory=dict)
    timeout: int = 3600


@dataclass
class BuildRecipe:
    machine: str
    baseline: str = "last_release_tag"
    suites: list = field(default_factory=list)
    pack: dict = field(default_factory=dict)
    release: dict = field(default_factory=dict)
    install_test: dict | None = None
    cache_dirs: list = field(default_factory=list)
    max_parallel_builds: int = 1
    channel: str = "#bobiverse"
    raw: dict = field(default_factory=dict)


class RecipeError(ValueError):
    pass


def recipe_path(repo_root: Path) -> Path:
    return Path(repo_root) / ".bobiverse" / "build.yml"


def load_recipe(repo_root: Path) -> BuildRecipe:
    path = recipe_path(repo_root)
    if not path.is_file():
        raise RecipeError(f"build: has no .bobiverse/build.yml; nothing started")
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        data = _parse_minimal_yaml(text)
    else:
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise RecipeError("build: recipe root must be a mapping")
    return validate_recipe(data)


def load_recipe_from_candidates(
    candidates: Iterable[Path] | list[Path] | tuple[Path, ...],
    *,
    repo: str = "",
    missing_kind: str = "build",
) -> BuildRecipe:
    """Load the first existing recipe under *candidates*.

    FR #6487: when a ``build.yml`` exists, propagate the real ``RecipeError``
    (missing PyYAML, validation, parse). The generic ``no .bobiverse/build.yml``
    line is reserved for when no candidate file is present.
    """
    for cand in candidates:
        root = Path(cand)
        if not recipe_path(root).is_file():
            continue
        return load_recipe(root)
    label = (repo or "").strip() or "repo"
    kind = (missing_kind or "build").strip() or "build"
    raise RecipeError(f"{kind}: {label} has no .bobiverse/build.yml; nothing started")


def validate_recipe(data: dict) -> BuildRecipe:
    if not isinstance(data, dict):
        raise RecipeError("build: recipe root must be a mapping")
    machine = str(data.get("machine") or "").strip()
    if not machine:
        raise RecipeError("build: recipe.machine is required")
    suites_raw = data.get("suites") or []
    if not isinstance(suites_raw, list) or not suites_raw:
        raise RecipeError("build: recipe.suites must be a non-empty list")
    suites: list[SuiteSpec] = []
    for i, s in enumerate(suites_raw):
        if not isinstance(s, dict):
            raise RecipeError(f"build: suites[{i}] must be a mapping")
        name = str(s.get("name") or "").strip()
        cmd = str(s.get("cmd") or "").strip()
        if not name or not cmd:
            raise RecipeError(f"build: suites[{i}] needs name and cmd")
        suites.append(
            SuiteSpec(
                name=name,
                cmd=cmd,
                cwd=str(s.get("cwd") or "."),
                env=dict(s.get("env") or {}),
                timeout=int(s.get("timeout") or 3600),
            )
        )
    pack = dict(data.get("pack") or {})
    release = dict(data.get("release") or {})
    install = data.get("install_test")
    if install is not None and not isinstance(install, dict):
        raise RecipeError("build: install_test must be a mapping when set")
    caches = list(data.get("cache_dirs") or [])
    try:
        max_p = int(data.get("max_parallel_builds") or 1)
    except (TypeError, ValueError) as exc:
        raise RecipeError("build: max_parallel_builds must be an int") from exc
    if max_p < 1:
        raise RecipeError("build: max_parallel_builds must be >= 1")
    return BuildRecipe(
        machine=machine,
        baseline=str(data.get("baseline") or "last_release_tag"),
        suites=suites,
        pack=pack,
        release=release,
        install_test=install,
        cache_dirs=caches,
        max_parallel_builds=max_p,
        channel=str(data.get("channel") or "#bobiverse"),
        raw=dict(data),
    )


def _parse_minimal_yaml(text: str) -> dict:
    """Tiny subset parser for tests when PyYAML is missing (top-level keys + nested lists)."""
    # Prefer json if the file is json-compatible; else require PyYAML for real recipes.
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    raise RecipeError("build: PyYAML required to parse build.yml (pip install pyyaml)")


# ------------------------------------------------------------------ classification


@dataclass(frozen=True)
class FailureClass:
    test_id: str
    kind: str  # new_regression | pre_existing | flaky | step_failure
    ref_failed: bool
    baseline_failed: bool
    solo_passed: bool = False


def classify_failure(
    test_id: str,
    *,
    ref_failed: bool,
    baseline_failed: bool,
    solo_passed: bool = False,
) -> FailureClass:
    """One solo rerun at ref: pass => flaky; else new vs pre-existing (FR #4006)."""
    tid = (test_id or "").strip()
    if not tid:
        raise ValueError("test_id required")
    if ref_failed and solo_passed:
        return FailureClass(tid, "flaky", True, baseline_failed, True)
    if ref_failed and not baseline_failed:
        return FailureClass(tid, "new_regression", True, False, False)
    if ref_failed and baseline_failed:
        return FailureClass(tid, "pre_existing", True, True, False)
    return FailureClass(tid, "pre_existing", ref_failed, baseline_failed, solo_passed)


def classify_step_failure(step: str) -> FailureClass:
    return FailureClass(f"step:{step}", "step_failure", True, False, False)


def has_pytest_session_or_summary(stdout: str) -> bool:
    """True when suite output shows pytest actually ran (FR #6644).

    A completed session (summary line or session banner) means failures are
    test failures, not missing-interpreter / command-not-found.
    """
    blob = str(stdout or "")
    if not blob.strip():
        return False
    low = blob.lower()
    if "test session starts" in low:
        return True
    if "short test summary info" in low:
        return True
    for line in reversed(blob.splitlines()):
        # FR #6647: keep skipped-only summary lines (e.g. ``===== 1 skipped =====``)
        # so the regex below can match; do not require passed|failed|error first.
        low_line = line.lower()
        if (
            "passed" not in low_line
            and "failed" not in low_line
            and "error" not in low_line
            and "skipped" not in low_line
        ):
            continue
        if re.search(r"(?i)\b\d+\s+(?:passed|failed|skipped|error)s?\b", line):
            return True
    return False


def is_command_not_found(stdout: str, exit_code: int) -> bool:
    """True when a suite failed because the shell could not start the command (FR #6490).

    Windows cmd uses exit 9009 and ``is not recognized``; Unix shells say
    ``command not found``. Real pytest failures must not match.

    FR #6644: a suite that produced a pytest session/summary is a test
    failure even when a traceback mentions ``FileNotFoundError`` + ``python``
    (e.g. WinError 3 long path inside a test). Only treat as environment
    failure when the command never started.
    """
    code = int(exit_code) if exit_code is not None else -1
    text = stdout or ""
    if has_pytest_session_or_summary(text):
        return False
    low = text.lower()
    if code == 9009:
        return True
    if "is not recognized as an internal or external command" in low:
        return True
    if "is not recognized as a command" in low:
        return True
    if "command not found" in low:
        return True
    if "filenotfounderror" in low and (
        "python" in low or "the system cannot find the file" in low
    ):
        return True
    return False


def suite_path_env_with_runner_python(env: dict | None = None) -> dict:
    """Prepend ``BOBIVERSE_PYTHON``'s directory (and ``Scripts``) to PATH (FR #6490)."""
    import os as _os
    import sys as _sys

    out = dict(env or {})
    py = (out.get("BOBIVERSE_PYTHON") or _os.environ.get("BOBIVERSE_PYTHON") or "").strip()
    if not py:
        py = (_sys.executable or "").strip()
    p = Path(py) if py else None
    if p is not None and p.is_file():
        dirs = [str(p.parent)]
        scripts = p.parent / "Scripts"
        if scripts.is_dir():
            dirs.append(str(scripts))
        cur = out.get("PATH")
        if cur is None:
            cur = _os.environ.get("PATH") or ""
        out["PATH"] = _os.pathsep.join(dirs + ([cur] if cur else []))
        out.setdefault("BOBIVERSE_PYTHON", str(p))
    return out


# FR #5121: pytest FAILED/ERROR nodeids — suite exit-code alone must not hide new failures.
_PYTEST_FAILED_NODEID_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-|\s*$)",
    re.MULTILINE,
)


def parse_pytest_failed_nodeids(text: str) -> set[str]:
    """Return pytest nodeids from FAILED/ERROR lines (set difference for build gate)."""
    out: set[str] = set()
    for m in _PYTEST_FAILED_NODEID_RE.finditer(text or ""):
        nid = (m.group(1) or "").strip()
        if nid:
            out.add(nid)
    return out


def new_failing_nodeids(ref_stdout: str, baseline_stdout: str) -> set[str]:
    """Nodeids failing at ref but not at baseline (incl. brand-new tests). FR #5121."""
    return parse_pytest_failed_nodeids(ref_stdout) - parse_pytest_failed_nodeids(baseline_stdout)


# Pytest CLI options that take a following value (FR #6561 solo path strip).
_PYTEST_OPTS_WITH_VALUE = frozenset(
    {
        "-c",
        "--config",
        "-k",
        "-m",
        "-o",
        "--override-ini",
        "-p",
        "-r",
        "-W",
        "--pythonwarnings",
        "-n",
        "--maxfail",
        "--tb",
        "--rootdir",
        "--basetemp",
        "--confcutdir",
        "--durations",
        "--junitxml",
        "--timeout",
        "--timeout-method",
        "--cov",
        "--cov-report",
        "--cov-config",
        "--log-cli-level",
        "--log-file",
        "--log-file-level",
    }
)


def _keep_pytest_option_tokens(args: list[str]) -> list[str]:
    """Keep pytest options; drop positional suite/path args (FR #6561)."""
    out: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            out.append(tok)
            if "=" in tok:
                i += 1
                continue
            if (
                tok in _PYTEST_OPTS_WITH_VALUE
                and i + 1 < len(args)
                and not str(args[i + 1]).startswith("-")
            ):
                out.append(args[i + 1])
                i += 2
                continue
            i += 1
            continue
        # Positional path / nodeid from the recipe — drop for solo.
        i += 1
    return out


def append_pytest_nodeid(cmd: str, nodeid: str) -> str:
    """Build a solo pytest command for one failing nodeid (FR #5121 / #6561).

    Keeps the interpreter, ``-m pytest`` (or bare ``pytest``) and every option.
    Drops positional suite/path args from the recipe command, then appends
    exactly one ``nodeid``. When the recipe has no positional path, behaviour
    matches the old append-only form.
    """
    import shlex

    c = (cmd or "").rstrip()
    n = (nodeid or "").strip()
    if not n:
        return c
    try:
        tokens = shlex.split(c, posix=True)
    except ValueError:
        tokens = c.split()
    if not tokens:
        return n

    pytest_idx: int | None = None
    for i, tok in enumerate(tokens):
        name = Path(str(tok).replace("\\", "/")).name.lower()
        if name in ("pytest", "pytest.exe", "py.test"):
            pytest_idx = i
            break
        if tok == "-m" and i + 1 < len(tokens) and tokens[i + 1] in ("pytest", "py.test"):
            pytest_idx = i + 1
            break
    if pytest_idx is None:
        # Unknown launcher — keep legacy append so classification still runs.
        return f"{c} {n}"

    head = tokens[: pytest_idx + 1]
    kept = _keep_pytest_option_tokens(tokens[pytest_idx + 1 :])
    return " ".join(head + kept + [n])


# ------------------------------------------------------------------ dedupe


def normalize_error_signature(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"0x[0-9a-f]+", "0xN", t)
    t = re.sub(r"\b\d{4,}\b", "N", t)
    return t[:240]


def issue_dedupe_key(*, test_id: str = "", error: str = "") -> str:
    raw = (test_id or "").strip() or normalize_error_signature(error)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def find_open_duplicate(
    open_issues: Iterable[dict],
    *,
    test_id: str = "",
    error: str = "",
) -> dict | None:
    """Return an open issue dict to comment on, or None to file new (one issue per root cause)."""
    key = issue_dedupe_key(test_id=test_id, error=error)
    needle = (test_id or "").strip().lower()
    sig = normalize_error_signature(error)
    for issue in open_issues:
        body = str(issue.get("body") or "")
        title = str(issue.get("title") or "")
        blob = f"{title}\n{body}".lower()
        if needle and needle in blob:
            return issue
        if f"dedupe:{key}" in blob:
            return issue
        if sig and sig[:40] and sig[:40] in normalize_error_signature(blob):
            return issue
    return None


def blocker_issue_body(
    *,
    repo: str,
    version: str,
    ref: str,
    failure: FailureClass,
    log_excerpt: str = "",
    build_url: str = "",
) -> str:
    return (
        f"## Release blocker ({version})\n\n"
        f"- repo: `{repo}`\n"
        f"- ref: `{ref}`\n"
        f"- kind: `{failure.kind}`\n"
        f"- test/step: `{failure.test_id}`\n"
        f"- baseline_failed: {failure.baseline_failed}\n"
        f"- solo_passed: {failure.solo_passed}\n"
        f"- dedupe:{issue_dedupe_key(test_id=failure.test_id)}\n"
        f"- build: {build_url or '(pending)'}\n\n"
        f"### Log excerpt\n```\n{(log_excerpt or '')[:2000]}\n```\n"
    )


# ------------------------------------------------------------------ single-flight lock


@dataclass
class BuildLock:
    """Per-repo single-flight; machine may allow parallel across repos up to max_parallel."""

    path: Path
    max_parallel: int = 1

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"builds": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"builds": {}}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def try_acquire(self, repo: str, build_id: str) -> tuple[bool, str]:
        repo = normalize_repo(repo)
        data = self._read()
        builds = data.setdefault("builds", {})
        existing = builds.get(repo)
        if existing:
            return False, str(existing.get("id") or existing)
        active = [k for k, v in builds.items() if v]
        if len(active) >= int(self.max_parallel):
            return False, f"machine_busy parallel={len(active)}/{self.max_parallel}"
        builds[repo] = {"id": build_id, "started": time.time()}
        self._write(data)
        return True, build_id

    def release(self, repo: str) -> None:
        repo = normalize_repo(repo)
        data = self._read()
        builds = data.setdefault("builds", {})
        builds.pop(repo, None)
        self._write(data)

    def running_id(self, repo: str) -> str | None:
        data = self._read()
        ent = (data.get("builds") or {}).get(normalize_repo(repo))
        if not ent:
            return None
        return str(ent.get("id") or ent)

    def age_s(self, repo: str, *, now: float | None = None) -> float | None:
        """Seconds since lock start, or None when unlocked / missing started."""
        data = self._read()
        ent = (data.get("builds") or {}).get(normalize_repo(repo))
        if not ent:
            return None
        try:
            started = float(ent.get("started") or 0)
        except (TypeError, ValueError):
            return None
        if started <= 0:
            return None
        return max(0.0, float(now if now is not None else time.time()) - started)

    def release_if_id(self, repo: str, build_id: str) -> bool:
        """FR #6491: release only when the held id matches ``build_id``."""
        repo = normalize_repo(repo)
        want = str(build_id or "").strip()
        if not want:
            return False
        data = self._read()
        builds = data.setdefault("builds", {})
        ent = builds.get(repo)
        if not ent:
            return False
        held = str(ent.get("id") or ent)
        if held != want:
            return False
        builds.pop(repo, None)
        self._write(data)
        return True

    def release_if_stale(
        self,
        repo: str,
        max_age_s: float,
        *,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """FR #6491: release when age exceeds ``max_age_s``. Returns (released, old_id)."""
        repo = normalize_repo(repo)
        try:
            limit = float(max_age_s)
        except (TypeError, ValueError):
            return False, ""
        if limit <= 0:
            return False, ""
        age = self.age_s(repo, now=now)
        if age is None or age <= limit:
            return False, str(self.running_id(repo) or "")
        old = str(self.running_id(repo) or "")
        self.release(repo)
        return True, old


def normalize_repo(repo: str) -> str:
    return (repo or "").strip().strip("/").lower()


def parse_repos_csv(raw: str) -> list[str]:
    out = []
    for part in (raw or "").split(","):
        p = part.strip()
        if not p:
            continue
        if not REPO_RE.match(p):
            raise ValueError(f"bad repo id: {p}")
        out.append(p)
    return out


# ------------------------------------------------------------------ !build parse / decide


@dataclass
class BuildDecision:
    ok: bool
    reason: str = ""
    pm_lines: list = field(default_factory=list)
    repos: list = field(default_factory=list)
    version: str = ""
    ref: str = ""
    dry_run: bool = False
    status_only: bool = False
    cancel: bool = False
    route: str = ""  # wire / queue hint for build machine


def parse_build(body: str) -> tuple[bool, str, str] | None:
    """Return (is_build, subcmd, rest) or None if not !build."""
    text = (body or "").strip()
    if not text.lower().startswith("!build"):
        return None
    parts = text.split(None, 2)
    if len(parts) == 1:
        return True, "", ""
    sub = parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""
    if sub in ("status", "cancel", "dry-run", "dryrun", "dry", "preflight"):
        return True, "dry-run" if sub in ("dry-run", "dryrun", "dry") else sub, rest
    # !build <repos> <version> [ref]
    return True, "run", text[len("!build") :].strip()


# #4186: WiX/MSI ProductVersion is numeric only -> refuse anything but x.y.z or x.y.z.w digits.
NUMERIC_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")


def version_refusal(version: str) -> str | None:
    """Return a refusal line when ``version`` is not purely numeric (x.y.z / x.y.z.w), else None."""
    v = version or ""
    if NUMERIC_VERSION_RE.match(v):
        return None
    return (
        f"build: refused version '{v}': must be numeric x.y.z or x.y.z.w (digits only, "
        f"e.g. 0.1.32 or 0.1.32.1; no 'v' prefix or -suffix; MSI/WiX needs a numeric version); nothing started"
    )


def decide_build(
    *,
    who,  # chair_commands.Principal
    body: str,
    may: Callable,
    denied_line: Callable,
    recipe_loader: Callable[[str], BuildRecipe | None],
    lock: BuildLock | None = None,
    ignored: Iterable[str] = (),
    new_build_id: Callable[[], str] | None = None,
    stale_max_age_s: float | None = None,
) -> BuildDecision | None:
    parsed = parse_build(body)
    if parsed is None:
        return None
    _, sub, rest = parsed
    if not may("build", who):
        return BuildDecision(False, "denied", [denied_line("build")])

    ignored_set = {normalize_repo(x) for x in ignored}

    if sub == "status":
        repo = (rest or "").strip()
        if repo:
            rid = lock.running_id(repo) if lock else None
            line = f"build status: {repo} running={rid or 'none'}"
        else:
            line = "build status: use !build status <owner/repo>"
        return BuildDecision(True, "status", [line], status_only=True)

    if sub == "cancel":
        repo = (rest or "").strip()
        if not repo or not REPO_RE.match(repo):
            return BuildDecision(False, "usage", ["build: usage !build cancel <owner/repo>"])
        if lock:
            lock.release(repo)
        return BuildDecision(True, "cancel", [f"build: cancelled lock for {repo}"], [repo], cancel=True)

    if sub == "preflight":
        # FR #6492: route a no-build environment check to the recipe machine.
        repo = (rest or "").strip().split()[0] if (rest or "").strip() else ""
        if not repo or not REPO_RE.match(repo):
            return BuildDecision(
                False,
                "usage",
                ["build: usage !build preflight <owner/repo>"],
            )
        if normalize_repo(repo) in ignored_set:
            return BuildDecision(
                False,
                "ignored",
                [f"build: {repo} is ignored; nothing started"],
                [repo],
            )
        try:
            recipe = recipe_loader(repo)
        except RecipeError as exc:
            return BuildDecision(
                False,
                "no_recipe",
                [str(exc) if str(exc).startswith("build:") else f"build: {repo} {exc}"],
                [repo],
            )
        if recipe is None:
            return BuildDecision(
                False,
                "no_recipe",
                [f"build: {repo} has no .bobiverse/build.yml; nothing started"],
                [repo],
            )
        route = f"BUILDPREFLIGHT v1 repo={repo}"
        return BuildDecision(
            True,
            "preflight",
            [
                f"build preflight: queued {repo} machine={recipe.machine} "
                f"(no build; checks runner Python, imports, suite python, "
                f"token source, recipe, work/cache dirs, pack tools)"
            ],
            [repo],
            route=route,
        )

    dry = sub == "dry-run"
    # run / dry-run: <repos> <version> [ref]
    arg = rest if dry else rest
    if dry and not arg:
        # !build dry-run <repos> <version>
        return BuildDecision(
            False,
            "usage",
            ["build: usage !build dry-run <owner/repo>[,owner/repo...] <version> [ref]"],
            dry_run=True,
        )
    tokens = arg.split()
    if len(tokens) < 2:
        return BuildDecision(
            False,
            "usage",
            [
                "build: usage !build <owner/repo>[,owner/repo...] <version> [ref]",
                "build: also !build status|cancel|dry-run|preflight ...",
            ],
            dry_run=dry,
        )
    try:
        repos = parse_repos_csv(tokens[0])
    except ValueError as exc:
        return BuildDecision(False, "bad_repo", [f"build: {exc}"], dry_run=dry)
    version = tokens[1]
    ref = tokens[2] if len(tokens) > 2 else "HEAD"
    refusal = version_refusal(version)
    if refusal:
        return BuildDecision(False, "bad_version", [refusal], dry_run=dry)
    if not repos:
        return BuildDecision(False, "usage", ["build: need at least one owner/repo"], dry_run=dry)

    lines: list[str] = []
    ok_repos: list[str] = []
    # FR #6491: one !build command shares one build id across its repos so the
    # BUILD v1 route and terminal BUILD ok/fail announces can match the chair lock.
    batch_id = (new_build_id or (lambda: f"b-{int(time.time())}"))()
    for repo in repos:
        if normalize_repo(repo) in ignored_set:
            lines.append(f"build: {repo} is ignored; nothing started")
            continue
        try:
            recipe = recipe_loader(repo)
        except RecipeError as exc:
            lines.append(str(exc) if str(exc).startswith("build:") else f"build: {repo} {exc}")
            continue
        if recipe is None:
            lines.append(f"build: {repo} has no .bobiverse/build.yml; nothing started")
            continue
        bid = batch_id
        if not dry and lock is not None:
            got, info = lock.try_acquire(repo, bid)
            if not got:
                # FR #6491: stale chair lock backstop (recipe max run, or explicit override).
                ttl = (
                    float(stale_max_age_s)
                    if stale_max_age_s is not None
                    else recipe_max_run_s(recipe)
                )
                released, old = lock.release_if_stale(repo, ttl)
                if released:
                    lines.append(
                        f"build: {repo} released stale lock id={old} age>{int(ttl)}s"
                    )
                    got, info = lock.try_acquire(repo, bid)
                if not got:
                    lines.append(f"build: {repo} refused; running id={info}")
                    continue
        ok_repos.append(repo)
        if dry:
            lines.append(
                f"build dry-run: {repo} version={version} ref={ref} "
                f"machine={recipe.machine} suites={len(recipe.suites)} "
                f"pack={'yes' if recipe.pack else 'no'} release={recipe.release.get('target') or '-'}"
            )
            lines.append(
                f"build dry-run: would classify ref vs baseline={recipe.baseline}; "
                f"file release-blocker issues for new_regression/step_failure; nothing published"
            )
        else:
            lines.append(
                f"build: queued {repo} version={version} ref={ref} "
                f"machine={recipe.machine} id={bid}"
            )
    if not ok_repos and not lines:
        lines.append("build: nothing started")
    route = ""
    if ok_repos and not dry:
        # FR #6491: put id= on the wire so the recipe machine and chair share it.
        route = (
            f"BUILD v1 repos={','.join(ok_repos)} version={version} "
            f"ref={ref} id={batch_id}"
        )
    return BuildDecision(
        bool(ok_repos) or dry and bool(lines),
        "dry_run" if dry else ("ok" if ok_repos else "refused"),
        lines,
        ok_repos,
        version,
        ref,
        dry,
        route=route,
    )


def dry_run_plan(recipe: BuildRecipe, *, repo: str, version: str, ref: str) -> list[str]:
    return [
        f"resolve recipe machine={recipe.machine} baseline={recipe.baseline}",
        f"run {len(recipe.suites)} suite(s) at {ref} and at baseline",
        "classify failures (new_regression / pre_existing / flaky)",
        f"pack={bool(recipe.pack)} release={recipe.release.get('target') or 'none'} version={version}",
        "file release-blocker issues for new regressions (dedupe by test id)",
        f"announce on {recipe.channel}",
    ]

# ------------------------------------------------------------------ WP2 runner (FR #4025)


BUILD_V1_RE = re.compile(
    r"^BUILD\s+v1\s+repos=(?P<repos>\S+)\s+version=(?P<version>\S+)\s+ref=(?P<ref>\S+)"
    r"(?:\s+id=(?P<id>\S+))?\s*$",
    re.IGNORECASE,
)

BUILDPREFLIGHT_V1_RE = re.compile(
    r"^BUILDPREFLIGHT\s+v1\s+repo=(?P<repo>\S+)\s*$",
    re.IGNORECASE,
)

# FR #6491: terminal result announces from the recipe machine (ok / fail / refuse shapes).
BUILD_RESULT_RE = re.compile(
    r"^BUILD\s+(?P<kind>ok|fail)\s+(?P<repo>\S+)"
    r"(?P<rest>.*?)"
    r"(?:\s+id=(?P<id>\S+))?\s*$",
    re.IGNORECASE,
)

# Backstop when recipe max-run cannot be computed (env overrideable).
DEFAULT_BUILD_LOCK_STALE_S = float(
    os.environ.get("BOBIVERSE_BUILD_LOCK_STALE_S") or (6 * 3600)
)

INSTALLTEST_V1_RE = re.compile(
    r"^INSTALLTEST\s+v1\s+repo=(?P<repo>\S+)\s+version=(?P<version>\S+)\s+tag=(?P<tag>\S+)\s*$",
    re.IGNORECASE,
)

# FR #6492: imports the SYSTEM runner must resolve (recipe YAML needs PyYAML).
BUILD_RUNNER_REQUIRED_IMPORTS = ("yaml",)

# Fallback DIGEST_ID_FOLD when bobreport is not importable (tests / slim envs).
_BUILD_ID_FOLD = {
    "ionos": "win-mpre8vi4u6u",
    "dev1": "ce-priority-dev1",
}


def render_template(text: str, **vars: Any) -> str:
    """Replace ``{{name}}`` placeholders; unknown keys left intact."""
    out = text if text is not None else ""
    for key, val in vars.items():
        out = out.replace("{{" + str(key) + "}}", str(val))
    return out


def parse_build_v1_route(text: str) -> dict | None:
    """Parse ``BUILD v1 repos=a,b version=X ref=Y`` -> dict or None."""
    raw = (text or "").strip()
    if raw.startswith(":"):
        raw = raw[1:].strip()
    m = BUILD_V1_RE.match(raw)
    if not m:
        return None
    repos_raw = m.group("repos")
    try:
        repos = parse_repos_csv(repos_raw)
    except ValueError:
        repos = [p for p in repos_raw.split(",") if p.strip()]
    return {
        "repos": repos,
        "version": m.group("version"),
        "ref": m.group("ref"),
        "id": (m.group("id") or "").strip(),
        "raw": raw,
    }


def parse_build_preflight_v1_route(text: str) -> dict | None:
    """FR #6492: parse ``BUILDPREFLIGHT v1 repo=owner/name`` -> dict or None."""
    raw = (text or "").strip()
    if raw.startswith(":"):
        raw = raw[1:].strip()
    m = BUILDPREFLIGHT_V1_RE.match(raw)
    if not m:
        return None
    repo = (m.group("repo") or "").strip()
    if not repo:
        return None
    return {"repo": repo, "raw": raw}


@dataclass
class PreflightItem:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PreflightReport:
    ok: bool
    exit_code: int = 0
    items: list = field(default_factory=list)
    lines: list = field(default_factory=list)


def _default_resolve_python(env: dict) -> str:
    """Resolved interpreter for the SYSTEM runner (BOBIVERSE_PYTHON, else sys.executable)."""
    import sys as _sys

    override = str((env or {}).get("BOBIVERSE_PYTHON") or "").strip()
    if override:
        return override
    return str(_sys.executable or "").strip()


def _default_missing_imports() -> list[str]:
    missing: list[str] = []
    for mod in BUILD_RUNNER_REQUIRED_IMPORTS:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    return missing


def _default_token_source() -> str:
    try:
        import gh_filer

        return str(gh_filer.ensure_gh_token_env() or "none")
    except Exception:
        for name in ("GH_TOKEN", "GITHUB_TOKEN"):
            if (os.environ.get(name) or "").strip():
                return f"env:{name}"
        return "none"


def _scrub_secret_fragments(text: str, env: dict | None = None) -> str:
    """Never echo token values in preflight details/lines."""
    out = str(text or "")
    secrets: list[str] = []
    src = env if env is not None else os.environ
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = str(src.get(key) or "").strip()
        if v and len(v) >= 8:
            secrets.append(v)
    for v in secrets:
        out = out.replace(v, "<redacted>")
    return out


# ------------------------------------------------------------------ build-work root / prune (FR #6655)


def resolve_build_work_root(env: dict | None = None) -> Path:
    """Parent folder for per-version build-work dirs (FR #6479 / #6655).

    Precedence: ``BOBIVERSE_BUILD_WORK_DIR``, else alias ``BOBIVERSE_BUILD_WORK``,
    else ``%ProgramData%/Bobiverse/build-work``.
    """
    e = env if env is not None else os.environ
    for key in ("BOBIVERSE_BUILD_WORK_DIR", "BOBIVERSE_BUILD_WORK"):
        override = str(e.get(key) or "").strip()
        if override:
            return Path(override)
    return Path(e.get("ProgramData", "C:/ProgramData")) / "Bobiverse" / "build-work"


def resolve_build_work_dir(
    version: str,
    *,
    work_dir_arg: str = "",
    env: dict | None = None,
) -> Path:
    """Resolve BUILD work directory for one version (FR #6479 / #6655).

    Precedence: ``--work-dir`` arg (as-is), else ``<root>/<version>``.
    """
    if (work_dir_arg or "").strip():
        return Path(work_dir_arg)
    return resolve_build_work_root(env) / str(version)


def build_work_min_free_gb(env: dict | None = None) -> float:
    """Free-space refuse threshold in GB (FR #6655). Default 2.0."""
    e = env if env is not None else os.environ
    raw = str(e.get("BOBIVERSE_BUILD_WORK_MIN_FREE_GB") or "2").strip()
    try:
        return float(raw)
    except ValueError:
        return 2.0


def build_work_keep_count(env: dict | None = None) -> int:
    """How many finished build-work dirs to keep (FR #6655). Default 2."""
    e = env if env is not None else os.environ
    raw = str(e.get("BOBIVERSE_BUILD_WORK_KEEP") or "2").strip()
    try:
        n = int(raw)
    except ValueError:
        return 2
    return max(0, n)


def volume_free_gb(path: Path | str) -> float:
    """Free space on the volume that holds ``path`` (GB)."""
    p = Path(path)
    probe = p if p.exists() else (p.anchor or p.drive or p.parent or Path("."))
    if not str(probe):
        probe = Path(".")
    usage = shutil.disk_usage(str(probe))
    return float(usage.free) / float(1024**3)


def _build_work_dir_idle(path: Path, *, now: float, idle_s: float) -> bool:
    """True when the dir looks finished/dead (no recent progress heartbeat)."""
    if idle_s <= 0:
        return True
    markers = ("progress.jsonl", "result.json", "runner.log")
    newest = 0.0
    try:
        newest = float(path.stat().st_mtime)
    except OSError:
        return True
    for name in markers:
        fp = path / name
        try:
            newest = max(newest, float(fp.stat().st_mtime))
        except OSError:
            continue
    return (now - newest) >= idle_s


def prune_build_work_dirs(
    root: Path | str,
    *,
    keep: int | None = None,
    active_names: Iterable[str] | None = None,
    idle_s: float = 6 * 3600,
    now: float | None = None,
    env: dict | None = None,
    remove: Callable[[Path], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Remove finished/dead build-work children, keeping the newest ``keep`` (FR #6655).

    Never removes names in ``active_names`` or dirs with a recent progress/
    result/runner heartbeat (``idle_s``, default 6h). Returns pruned paths.
    """
    base = Path(root)
    if not base.is_dir():
        return []
    keep_n = build_work_keep_count(env) if keep is None else max(0, int(keep))
    active = {str(x).strip().lower() for x in (active_names or []) if str(x).strip()}
    ts = float(time.time() if now is None else now)
    remove_fn = remove or (lambda p: shutil.rmtree(p, ignore_errors=True))
    log_fn = log or (lambda _m: None)

    children: list[tuple[float, Path]] = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if child.name.strip().lower() in active:
            continue
        if not _build_work_dir_idle(child, now=ts, idle_s=idle_s):
            continue
        try:
            mtime = float(child.stat().st_mtime)
        except OSError:
            mtime = 0.0
        children.append((mtime, child))
    children.sort(key=lambda row: row[0], reverse=True)
    pruned: list[str] = []
    for _mtime, child in children[keep_n:]:
        try:
            remove_fn(child)
            pruned.append(str(child))
            log_fn(f"build: pruned work dir {child}")
        except Exception as exc:
            log_fn(f"build: prune failed path={child} err={type(exc).__name__}")
    return pruned


def run_build_preflight(
    *,
    repo: str,
    repo_root: Path | str,
    env: dict | None = None,
    which: Callable | None = None,
    resolve_python: Callable | None = None,
    missing_imports: Callable | None = None,
    token_source: Callable | None = None,
    gh_auth: Callable | None = None,
    recipe_loader: Callable | None = None,
    work_dir: Path | str | None = None,
    mkdir: Callable | None = None,
    free_gb: Callable[[Path], float] | None = None,
    pack_tools: tuple[str, ...] = ("powershell", "gh"),
) -> PreflightReport:
    """FR #6492: recipe-machine environment check (no suite/pack/release).

    Each item is reported as ``build preflight: <name>=ok|missing <detail>``.
    Exit code 0 only when every item is ok. Never includes token values.
    FR #6655: ``work_dir_free`` refuses when the build-work volume is under
    ``BOBIVERSE_BUILD_WORK_MIN_FREE_GB`` (default 2).
    """
    e = dict(os.environ if env is None else env)
    which_fn = which or shutil.which
    resolve_py = resolve_python or _default_resolve_python
    miss_imp = missing_imports or _default_missing_imports
    tok_src = token_source or _default_token_source
    auth_fn = gh_auth or (lambda: gh_auth_preflight(env=e))
    load_fn = recipe_loader or load_recipe
    mkdir_fn = mkdir or (lambda p: Path(p).mkdir(parents=True, exist_ok=True))
    free_fn = free_gb or volume_free_gb

    root = Path(repo_root)
    if work_dir is None:
        work = resolve_build_work_root(e) / "preflight"
    else:
        work = Path(work_dir)

    items: list[PreflightItem] = []

    # 1) resolved runner Python (BOBIVERSE_PYTHON / sys.executable)
    py_path = str(resolve_py(e) or "").strip()
    if py_path:
        items.append(PreflightItem("runner_python", True, f"path={py_path}"))
    else:
        items.append(
            PreflightItem(
                "runner_python",
                False,
                "set NSSM AppEnvironmentExtra BOBIVERSE_PYTHON to the full python.exe path",
            )
        )

    # 2) required imports in that interpreter's environment (this process for tests)
    missing = list(miss_imp() or [])
    if missing:
        items.append(
            PreflightItem(
                "runner_imports",
                False,
                "missing=" + ",".join(missing) + " (pip install pyyaml into BOBIVERSE_PYTHON)",
            )
        )
    else:
        items.append(
            PreflightItem(
                "runner_imports",
                True,
                "ok=" + ",".join(BUILD_RUNNER_REQUIRED_IMPORTS),
            )
        )

    # 3) suite Python on PATH (suites invoke bare `python`)
    suite_py = which_fn("python")
    if suite_py:
        items.append(PreflightItem("suite_python", True, f"path={suite_py}"))
    else:
        items.append(
            PreflightItem(
                "suite_python",
                False,
                "python not on PATH; add Python312 + Scripts to ircBob PATH (FR #6490)",
            )
        )

    # 4) GitHub token source tag only (never value)
    src_tag = _scrub_secret_fragments(str(tok_src() or "none"), e)
    auth_err = auth_fn()
    if src_tag == "none" or auth_err:
        detail = f"source={src_tag}"
        if auth_err:
            detail += " " + _scrub_secret_fragments(str(auth_err).split(":")[0], e)
        items.append(
            PreflightItem(
                "github_token",
                False,
                detail + "; put token in <install>\\config\\github.token (SYSTEM+Administrators ACL)",
            )
        )
    else:
        items.append(PreflightItem("github_token", True, f"source={src_tag}"))

    # 5) recipe parse
    recipe = None
    try:
        recipe = load_fn(root)
        items.append(
            PreflightItem(
                "recipe",
                True,
                f"machine={getattr(recipe, 'machine', '-') } suites={len(getattr(recipe, 'suites', []) or [])}",
            )
        )
    except Exception as exc:
        items.append(
            PreflightItem(
                "recipe",
                False,
                _scrub_secret_fragments(str(exc)[:160], e),
            )
        )

    # 6) work dir creatable
    try:
        mkdir_fn(work)
        items.append(PreflightItem("work_dir", True, f"path={work}"))
    except Exception as exc:
        items.append(
            PreflightItem(
                "work_dir",
                False,
                f"path={work} err={type(exc).__name__}",
            )
        )

    # 6b) FR #6655: build-work volume free space (refuse under threshold)
    min_free = build_work_min_free_gb(e)
    try:
        free = float(free_fn(work))
        detail = f"free_gb={free:.2f} min_gb={min_free:.2f} path={work}"
        if free < min_free:
            items.append(
                PreflightItem(
                    "work_dir_free",
                    False,
                    detail + "; set BOBIVERSE_BUILD_WORK(_DIR) to a roomy volume or free space",
                )
            )
        else:
            items.append(PreflightItem("work_dir_free", True, detail))
    except Exception as exc:
        items.append(
            PreflightItem(
                "work_dir_free",
                False,
                f"path={work} err={type(exc).__name__}",
            )
        )

    # 7) cache dir creatable (under work/cache + recipe cache_dirs)
    cache_root = work / "cache"
    try:
        mkdir_fn(cache_root)
        for rel in (getattr(recipe, "cache_dirs", None) or []) if recipe is not None else []:
            mkdir_fn(cache_root / str(rel))
        items.append(PreflightItem("cache_dir", True, f"path={cache_root}"))
    except Exception as exc:
        items.append(
            PreflightItem(
                "cache_dir",
                False,
                f"path={cache_root} err={type(exc).__name__}",
            )
        )

    # 8) pack tools on PATH (powershell + gh for Pack-*/Assert-*/release)
    missing_tools = [t for t in pack_tools if not which_fn(t)]
    if missing_tools:
        items.append(
            PreflightItem(
                "pack_tools",
                False,
                "missing=" + ",".join(missing_tools),
            )
        )
    else:
        items.append(
            PreflightItem(
                "pack_tools",
                True,
                "ok=" + ",".join(pack_tools),
            )
        )

    lines: list[str] = []
    for it in items:
        status = "ok" if it.ok else "missing"
        detail = _scrub_secret_fragments(it.detail, e)
        lines.append(f"build preflight: {it.name}={status}" + (f" {detail}" if detail else ""))
    all_ok = all(i.ok for i in items)
    return PreflightReport(ok=all_ok, exit_code=0 if all_ok else 1, items=items, lines=lines)

def parse_build_result(text: str) -> dict | None:
    """FR #6491: parse ``BUILD ok|fail <repo> ... [id=...]`` terminal announce.

    Returns dict with ``kind`` (ok/fail), ``repo``, ``id`` (may be empty), ``raw``;
    None when the line is not a terminal BUILD result (e.g. BUILD v1 route).
    """
    raw = (text or "").strip()
    if raw.startswith(":"):
        raw = raw[1:].strip()
    if not raw.upper().startswith("BUILD "):
        return None
    # Route / started / release / blocker chatter is not a terminal result.
    head = raw.split(None, 2)
    if len(head) < 3:
        return None
    kind = head[1].lower()
    if kind not in ("ok", "fail"):
        return None
    m = BUILD_RESULT_RE.match(raw)
    if not m:
        return None
    repo = (m.group("repo") or "").strip()
    if not repo or repo.lower().startswith("v1"):
        return None
    # Trailing id= may sit inside rest when optional group missed (colon shapes).
    rid = (m.group("id") or "").strip()
    if not rid:
        im = re.search(r"(?:^|\s)id=(\S+)\s*$", raw, re.IGNORECASE)
        if im:
            rid = im.group(1).strip()
    return {
        "kind": kind,
        "repo": repo,
        "id": rid,
        "raw": raw,
    }


def apply_build_result_to_chair_lock(lock: BuildLock, result: dict | None) -> bool:
    """FR #6491: release chair lock when result id matches the held id."""
    if not result or lock is None:
        return False
    repo = str(result.get("repo") or "").strip()
    bid = str(result.get("id") or "").strip()
    if not repo or not bid:
        return False
    return lock.release_if_id(repo, bid)


def recipe_max_run_s(recipe: BuildRecipe | None, *, cap: float | None = None) -> float:
    """FR #6491: stale-lock TTL = suite timeouts (ref+baseline) + pack/release budget.

    When ``recipe`` is missing, returns ``cap`` or ``DEFAULT_BUILD_LOCK_STALE_S``.
    """
    limit = float(cap) if cap is not None else float(DEFAULT_BUILD_LOCK_STALE_S)
    if recipe is None:
        return limit
    suite_s = 0.0
    for s in recipe.suites or []:
        try:
            suite_s += float(getattr(s, "timeout", None) or 3600) * 2.0  # ref + baseline
        except (TypeError, ValueError):
            suite_s += 7200.0
    pack_s = 1800.0 if recipe.pack else 0.0
    release_s = 1800.0 if (recipe.release or {}).get("target") else 0.0
    computed = suite_s + pack_s + release_s + 600.0
    return max(computed, 1.0)


def fold_build_machine(mid: str) -> str:
    """DIGEST_ID_FOLD: ``ionos`` -> ``win-mpre8vi4u6u`` (canonical). Prefer bobreport."""
    s = str(mid or "").strip().lstrip("#").lower()
    if not s:
        return ""
    try:
        from bobreport import fold_machine_id  # type: ignore

        folded = fold_machine_id(s)
        if folded:
            return str(folded).strip().lower()
    except Exception:
        pass
    s = _BUILD_ID_FOLD.get(s, s)
    return re.sub(r"[^a-z0-9._-]+", "", s) or s


def is_recipe_build_machine(recipe_machine: str, local_machine: str) -> bool:
    """True when local host is the recipe machine (alias-aware)."""
    a = fold_build_machine(recipe_machine)
    b = fold_build_machine(local_machine)
    return bool(a) and bool(b) and a == b


class GitHubFiler:
    """Live GitHub issue API via `gh` CLI (inject FakeGitHubFiler in tests).

    FR #4025: WP2 must file release-blocker issues on the recipe machine without agent
    tokens. Abstract NotImplementedError would leave live `run_bobiverse_build` unable
    to file blockers (MRB #4072).
    """

    def __init__(self, *, gh_runner: Callable | None = None) -> None:
        self._gh = gh_runner

    def _run_gh(self, args: list[str]) -> str:
        import subprocess as _sp

        runner = self._gh or _sp.run
        completed = runner(
            ["gh", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        # support both CompletedProcess and injectable callables returning the same
        code = int(getattr(completed, "returncode", 0) or 0)
        out = getattr(completed, "stdout", "") or ""
        err = getattr(completed, "stderr", "") or ""
        if code != 0:
            raise RuntimeError(f"gh {' '.join(args)} failed rc={code}: {err or out}")
        return out

    def list_open_issues(self, repo: str) -> list[dict]:
        raw = self._run_gh(
            [
                "issue",
                "list",
                "--repo",
                normalize_repo(repo),
                "--state",
                "open",
                "--limit",
                "100",
                "--json",
                "number,title,body,labels,state",
            ]
        )
        import json as _json

        items = _json.loads(raw or "[]")
        out = []
        for it in items:
            labels = it.get("labels") or []
            names = []
            for lab in labels:
                if isinstance(lab, dict):
                    names.append(str(lab.get("name") or ""))
                else:
                    names.append(str(lab))
            out.append(
                {
                    "number": int(it.get("number") or 0),
                    "title": str(it.get("title") or ""),
                    "body": str(it.get("body") or ""),
                    "labels": names,
                    "state": str(it.get("state") or "open"),
                }
            )
        return out

    def create_issue(
        self, repo: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        args = [
            "issue",
            "create",
            "--repo",
            normalize_repo(repo),
            "--title",
            title,
            "--body",
            body,
        ]
        for lab in labels or []:
            args.extend(["--label", str(lab)])
        raw = self._run_gh(args)
        # gh prints the issue URL on success
        number = 0
        import re as _re

        m = _re.search(r"/issues/(\d+)", raw or "")
        if m:
            number = int(m.group(1))
        return {
            "number": number,
            "title": title,
            "body": body,
            "labels": list(labels or []),
            "state": "open",
            "url": (raw or "").strip(),
        }

    def comment(self, repo: str, number: int, body: str) -> dict:
        self._run_gh(
            [
                "issue",
                "comment",
                str(int(number)),
                "--repo",
                normalize_repo(repo),
                "--body",
                body,
            ]
        )
        return {"repo": normalize_repo(repo), "number": int(number), "body": body}


class FakeGitHubFiler(GitHubFiler):
    """In-memory filer for unit tests."""

    def __init__(self) -> None:
        self.issues: dict[str, list[dict]] = {}
        self.comments: list[dict] = []
        self._next = 1

    def list_open_issues(self, repo: str) -> list[dict]:
        key = normalize_repo(repo)
        return list(self.issues.get(key, []))

    def create_issue(
        self, repo: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        key = normalize_repo(repo)
        num = self._next
        self._next += 1
        issue = {
            "number": num,
            "title": title,
            "body": body,
            "labels": list(labels or []),
            "state": "open",
            "repo": key,
            "url": f"https://github.com/{key}/issues/{num}",
        }
        self.issues.setdefault(key, []).append(issue)
        return issue

    def comment(self, repo: str, number: int, body: str) -> dict:
        ent = {"repo": normalize_repo(repo), "number": int(number), "body": body}
        self.comments.append(ent)
        return ent


def file_blocker_or_dedupe(
    filer: GitHubFiler,
    *,
    repo: str,
    version: str,
    ref: str,
    failure: FailureClass,
    log_excerpt: str = "",
    build_url: str = "",
    extra_labels: Iterable[str] | None = None,
) -> dict:
    """Create release-blocker FR or comment on an open duplicate (one issue per root cause)."""
    open_issues = filer.list_open_issues(repo)
    hit = find_open_duplicate(open_issues, test_id=failure.test_id)
    body = blocker_issue_body(
        repo=repo,
        version=version,
        ref=ref,
        failure=failure,
        log_excerpt=log_excerpt,
        build_url=build_url,
    )
    labels = [FEATURE_REQUEST_LABEL, RELEASE_BLOCKER_LABEL]
    for lab in extra_labels or []:
        s = str(lab).strip()
        if s and s not in labels:
            labels.append(s)
    repo_n = normalize_repo(repo)
    if hit:
        number = int(hit["number"])
        note = (
            f"BUILD re-hit {failure.kind} for `{failure.test_id}` "
            f"version={version} ref={ref}\n\n{body}"
        )
        filer.comment(repo, number, note)
        return {
            "action": "commented",
            "number": number,
            "repo": repo_n,
            "kind": failure.kind,
            "test_id": failure.test_id,
            "url": f"https://github.com/{repo_n}/issues/{number}",
            "labels": labels,
        }
    title = f"release-blocker: {failure.test_id} ({version})"
    created = filer.create_issue(repo, title, body, labels=labels)
    number = int(created["number"])
    url = str(created.get("url") or "").strip() or f"https://github.com/{repo_n}/issues/{number}"
    return {
        "action": "created",
        "number": number,
        "repo": repo_n,
        "kind": failure.kind,
        "test_id": failure.test_id,
        "url": url,
        "labels": labels,
    }


def file_runner_abort_blocker(
    filer: GitHubFiler,
    *,
    repo: str,
    version: str,
    ref: str,
    exc: BaseException,
    suite_name: str = "",
) -> dict:
    """FR #4316: auto-file for LiveStateTouched / unexpected runner aborts (machine:any)."""
    if isinstance(exc, LiveStateTouched):
        step = f"guard:LiveStateTouched:{suite_name or 'build'}"
    else:
        step = f"runner:{suite_name or 'build'}:{type(exc).__name__}"
    failure = classify_step_failure(step)
    return file_blocker_or_dedupe(
        filer,
        repo=repo,
        version=version,
        ref=ref,
        failure=failure,
        log_excerpt=f"{type(exc).__name__}: {exc}",
        extra_labels=[MACHINE_ANY_LABEL],
    )


@dataclass
class SuiteRunResult:
    name: str
    ref_or_baseline: str
    exit_code: int
    stdout: str
    timed_out: bool
    duration_s: float


@dataclass
class BuildReport:
    ok: bool
    blockers_filed: list = field(default_factory=list)
    suite_results: list = field(default_factory=list)
    pack_ok: bool = False
    release_ok: bool = False
    log_zip: str = ""
    announce_lines: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ------------------------------------------------------------------ FR #6585 progress


_CRED_PATH_RE = re.compile(
    r"(?i)(?:[/\\]|^)(?:\.config[/\\]gh[/\\]hosts\.yml|github\.token|\.password|identity\.json|"
    r"\.netrc|credentials\.json)(?=\b|/|\\|$)"
)
_GHP_TOKEN_RE = re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}")


def parse_pytest_summary_counts(text: str) -> dict[str, int]:
    """Best-effort pytest summary counts from suite stdout (FR #6585)."""
    out = {"passed": 0, "failed": 0, "skipped": 0}
    blob = str(text or "")
    # Prefer the final ``===== N passed, ... =====`` style line.
    for line in reversed(blob.splitlines()):
        if "passed" not in line.lower() and "failed" not in line.lower():
            continue
        if "=====" not in line and "passed" not in line.lower():
            continue
        m_pass = re.search(r"(?i)\b(\d+)\s+passed\b", line)
        m_fail = re.search(r"(?i)\b(\d+)\s+failed\b", line)
        m_skip = re.search(r"(?i)\b(\d+)\s+skipped\b", line)
        if m_pass or m_fail or m_skip:
            if m_pass:
                out["passed"] = int(m_pass.group(1))
            if m_fail:
                out["failed"] = int(m_fail.group(1))
            if m_skip:
                out["skipped"] = int(m_skip.group(1))
            return out
    return out


def redact_build_progress_text(text: str, env: dict | None = None) -> str:
    """Strip secrets / credential-shaped paths from a progress line (FR #6585)."""
    out = _scrub_secret_fragments(str(text or ""), env=env)
    out = _GHP_TOKEN_RE.sub("<redacted>", out)
    out = _BEARER_RE.sub("Bearer <redacted>", out)
    out = _CRED_PATH_RE.sub("<redacted-path>", out)
    return out


class JsonlProgressSink:
    """Append one JSON object per progress line (ear watcher tails this file)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def __call__(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "line": str(line)}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
            fh.flush()


def read_progress_jsonl(
    path: Path | str, *, after_offset: int = 0
) -> list[dict]:
    """Read progress JSONL rows starting at *after_offset* bytes (FR #6585)."""
    p = Path(path)
    if not p.is_file():
        return []
    size = p.stat().st_size
    off = max(0, int(after_offset or 0))
    if off >= size:
        return []
    with p.open("rb") as fh:
        fh.seek(off)
        raw = fh.read().decode("utf-8", errors="replace")
    rows: list[dict] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("line"):
            rows.append(obj)
    return rows


class BuildProgressPoster:
    """Rate-limited BUILD progress lines for #bobiverse (FR #6585).

    * At most one non-forced line every ``min_interval_s`` (default 30).
    * Heartbeat when nothing posted for ``heartbeat_s`` (default 600).
    * Every line carries ``version=`` and optional ``id=``.
    * Sink failures never raise into the build.
    * Terminal ``BUILD ok|fail`` announces stay separate (unchanged).
    """

    def __init__(
        self,
        *,
        repo: str,
        version: str,
        build_id: str = "",
        sink: Callable[[str], None] | None = None,
        min_interval_s: float = 30.0,
        heartbeat_s: float = 600.0,
        time_fn: Callable[[], float] | None = None,
        env: dict | None = None,
    ) -> None:
        self.repo = str(repo or "").strip()
        self.version = str(version or "").strip()
        self.build_id = str(build_id or "").strip()
        self.sink = sink
        self.min_interval_s = float(min_interval_s)
        self.heartbeat_s = float(heartbeat_s)
        self.time_fn = time_fn or time.time
        self.env = env
        self._last_post_at: float | None = None
        self._run_started_at = float(self.time_fn())
        self._current_step = "starting"
        self._step_started_at = self._run_started_at
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

    def start_heartbeat_thread(self, *, poll_s: float = 30.0) -> None:
        """Daemon thread: post heartbeat when idle for ``heartbeat_s`` (FR #6585)."""
        if self._hb_thread is not None:
            return

        def _loop() -> None:
            while not self._hb_stop.wait(timeout=max(5.0, float(poll_s))):
                with contextlib.suppress(Exception):
                    self.maybe_heartbeat()

        self._hb_thread = threading.Thread(
            target=_loop, name="build-progress-hb", daemon=True
        )
        self._hb_thread.start()

    def stop_heartbeat_thread(self) -> None:
        self._hb_stop.set()

    def set_current_step(self, step: str) -> None:
        self._current_step = str(step or "").strip() or "running"
        self._step_started_at = float(self.time_fn())

    def _id_bit(self) -> str:
        return f" id={self.build_id}" if self.build_id else ""

    def format_line(self, detail: str) -> str:
        detail_s = redact_build_progress_text(detail, env=self.env).strip()
        return (
            f"BUILD progress {self.repo} version={self.version} "
            f"{detail_s}{self._id_bit()}"
        ).strip()

    def emit(self, detail: str, *, force: bool = False) -> bool:
        """Post one progress line. Returns True when the sink was invoked."""
        now = float(self.time_fn())
        if (
            not force
            and self._last_post_at is not None
            and (now - self._last_post_at) < self.min_interval_s
        ):
            return False
        line = self.format_line(detail)
        if self.sink is None:
            self._last_post_at = now
            return True
        try:
            self.sink(line)
        except Exception:
            return False
        self._last_post_at = now
        return True

    def maybe_heartbeat(self) -> bool:
        now = float(self.time_fn())
        if self._last_post_at is None:
            return False
        if (now - self._last_post_at) < self.heartbeat_s:
            return False
        step = self._current_step
        step_age = max(0, int(now - self._step_started_at))
        run_age = max(0, int(now - self._run_started_at))
        return self.emit(
            f"heartbeat step={step} step_s={step_age} run_s={run_age}",
            force=True,
        )

    def step_start(self, step: str) -> bool:
        self.set_current_step(step)
        return self.emit(f"step start {step}", force=True)

    def step_end(self, step: str, *, ok: bool | None = None) -> bool:
        now = float(self.time_fn())
        elapsed = max(0, int(now - self._step_started_at))
        bit = ""
        if ok is True:
            bit = " ok"
        elif ok is False:
            bit = " fail"
        return self.emit(f"step end {step} elapsed={elapsed}s{bit}", force=True)

    def suite_counts(self, suite: str, *, at: str, stdout: str) -> bool:
        c = parse_pytest_summary_counts(stdout)
        return self.emit(
            f"suite {suite} at={at} passed={c['passed']} failed={c['failed']} "
            f"skipped={c['skipped']}",
            force=True,
        )

    def rerun_progress(
        self, *, index: int, total: int, nodeid: str, result: str
    ) -> bool:
        """Solo rerun lines: flood-safe with bookends + fails always visible.

        FR #6585 rate-limits progress (~30s). Passing solos in a fast burst are
        rate-limited; first/last index and fail/timeout always force so operators
        still see progress without hundreds of pass lines.
        """
        nid = redact_build_progress_text(nodeid, env=self.env)
        # Short nodeid for channel flood safety.
        if len(nid) > 80:
            nid = nid[:77] + "..."
        res = str(result or "").strip().lower()
        force = (
            index <= 1
            or index >= int(total or 0)
            or res in ("fail", "timeout", "error")
        )
        return self.emit(
            f"rerun {index}/{total} {nid} {result}",
            force=force,
        )


def run_command(
    cmd: str | list,
    cwd: str | Path | None = None,
    env: dict | None = None,
    timeout: float | None = None,
    runner: Any = None,
    *,
    name: str = "cmd",
    ref_or_baseline: str = "",
    log_path: str | Path | None = None,
) -> SuiteRunResult:
    """Run a shell command with hard timeout (FR #3965 class). Injectable ``runner``.

    On timeout the process is killed and ``timed_out=True`` (exit_code=-1).

    FR #6586: when ``log_path`` is set, stdout is streamed line-by-line into that
    file with an immediate flush so a killed mid-suite build keeps partial output
    (including failing nodeids seen so far). Injectable fakes without ``stdout``
    still use ``communicate``.
    """
    import subprocess as _sp
    import threading

    sp = runner if runner is not None else _sp
    cwd_s = str(cwd) if cwd is not None else None
    import os as _os

    # FR #6490: always start from process env and put BOBIVERSE_PYTHON on PATH so
    # recipe ``python ...`` matches the runner interpreter under SYSTEM / NSSM.
    env_map = dict(_os.environ)
    if env:
        env_map.update({str(k): str(v) for k, v in env.items()})
    env_map = suite_path_env_with_runner_python(env_map)
    t0 = time.time()
    timed_out = False
    exit_code = -1
    stdout = ""
    log_fp = None
    chunks: list[str] = []
    try:
        if log_path is not None:
            lp = Path(log_path)
            lp.parent.mkdir(parents=True, exist_ok=True)
            # Line-buffered text so a hard kill still leaves flushed lines on disk.
            log_fp = open(lp, "w", encoding="utf-8", newline="", buffering=1)
        popen_kw = dict(
            cwd=cwd_s,
            env=env_map,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
        if isinstance(cmd, (list, tuple)):
            proc = sp.Popen(list(cmd), **popen_kw)
        else:
            proc = sp.Popen(str(cmd), shell=True, **popen_kw)

        stream = getattr(proc, "stdout", None)
        if stream is not None and hasattr(stream, "readline"):
            pump_err: list[BaseException] = []

            def _pump() -> None:
                try:
                    while True:
                        line = stream.readline()
                        if line == "" or line is None:
                            break
                        if isinstance(line, bytes):
                            try:
                                line = line.decode("utf-8", "replace")
                            except Exception:
                                line = str(line)
                        chunks.append(line)
                        if log_fp is not None:
                            try:
                                log_fp.write(line)
                                log_fp.flush()
                            except Exception:
                                pass
                except BaseException as exc:  # pragma: no cover - pump best-effort
                    pump_err.append(exc)

            pump = threading.Thread(target=_pump, name=f"build-pump-{name}", daemon=True)
            pump.start()
            try:
                if timeout is None:
                    exit_code = int(proc.wait() if proc.returncode is None else proc.returncode)
                else:
                    try:
                        exit_code = int(proc.wait(timeout=float(timeout)))
                    except Exception:
                        timed_out = True
                        exit_code = -1
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            pass
            finally:
                pump.join(timeout=2.0)
            stdout = "".join(chunks)
            if timed_out:
                stdout = (stdout or "") + f"\n[timed_out after {timeout}s]"
            if proc.returncode is not None and not timed_out:
                exit_code = int(proc.returncode)
        else:
            # Injectable FakeSp / no-stdout path (FR #4025 timeout tests).
            try:
                out, _ = proc.communicate(timeout=timeout)
                stdout = out or ""
                exit_code = int(proc.returncode if proc.returncode is not None else -1)
            except Exception as exc:
                timed_out = True
                exit_code = -1
                raw_out = getattr(exc, "output", None) or getattr(exc, "stdout", None) or ""
                if isinstance(raw_out, bytes):
                    try:
                        stdout = raw_out.decode("utf-8", "replace")
                    except Exception:
                        stdout = str(raw_out)
                else:
                    stdout = str(raw_out) if raw_out else ""
                stdout = (stdout or "") + f"\n[timed_out after {timeout}s]"
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
            if log_fp is not None and stdout:
                try:
                    log_fp.write(stdout)
                    log_fp.flush()
                except Exception:
                    pass
    except Exception as exc:
        stdout = f"{type(exc).__name__}: {exc}"
        exit_code = -1
    finally:
        if log_fp is not None:
            try:
                log_fp.flush()
            except Exception:
                pass
            try:
                log_fp.close()
            except Exception:
                pass
    return SuiteRunResult(
        name=name,
        ref_or_baseline=ref_or_baseline,
        exit_code=exit_code,
        stdout=stdout,
        timed_out=timed_out,
        duration_s=max(0.0, time.time() - t0),
    )


class BuildRunner:
    """Deterministic live BUILD executor (no agent tokens). Fully injectable for tests.

    Pack and release run only when there are no ``new_regression`` / ``step_failure``
    blockers (pre_existing / flaky do not block pack).
    """

    def __init__(
        self,
        repo_root: Path | str,
        repo: str,
        version: str,
        ref: str,
        recipe: BuildRecipe,
        filer: GitHubFiler,
        *,
        work_dir: Path | str,
        log_dir: Path | str,
        local_machine: str,
        run_command_fn: Callable | None = None,
        pack_fn: Callable | None = None,
        release_fn: Callable | None = None,
        baseline_resolver: Callable | None = None,
        baseline_root: Path | str | None = None,
        build_id: str = "",
        progress: BuildProgressPoster | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        # Baseline suites run in their own checkout of the baseline tag; without one
        # they would re-run the ref tree and every failure would look pre-existing.
        self.baseline_root = Path(baseline_root) if baseline_root else None
        self.repo = repo
        self.version = version
        self.ref = ref
        self.recipe = recipe
        self.filer = filer
        self.work_dir = Path(work_dir)
        self.log_dir = Path(log_dir)
        self.local_machine = local_machine
        self.run_command_fn = run_command_fn or run_command
        self.pack_fn = pack_fn
        self.release_fn = release_fn
        self.baseline_resolver = baseline_resolver
        self.build_id = str(build_id or "").strip()
        # FR #6585: optional live progress sink (ear tails JSONL -> #bobiverse).
        self.progress = progress

    def _progress(self) -> BuildProgressPoster | None:
        return self.progress

    def _prog_heartbeat(self) -> None:
        prog = self._progress()
        if prog is not None:
            with contextlib.suppress(Exception):
                prog.maybe_heartbeat()

    def _id_suffix(self) -> str:
        """FR #6491: append `` id=<build_id>`` to terminal announces when set."""
        return f" id={self.build_id}" if self.build_id else ""

    def _ensure_dirs(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Persistent download cache: BOBIVERSE_DOWNLOAD_CACHE may override; default
        # work_dir/cache. Recipe cache_dirs are created under that cache root so
        # Fetch-* scripts can reuse bits across builds.
        import os as _os

        cache_root = Path(
            (_os.environ.get("BOBIVERSE_DOWNLOAD_CACHE") or "").strip()
            or (self.work_dir / "cache")
        )
        cache_root.mkdir(parents=True, exist_ok=True)
        for rel in self.recipe.cache_dirs or []:
            (cache_root / str(rel)).mkdir(parents=True, exist_ok=True)

    def _resolve_baseline(self) -> str:
        if self.baseline_resolver is not None:
            return str(self.baseline_resolver(self.recipe, self.repo_root, self.ref))
        return "baseline"

    def _write_log(self, name: str, text: str) -> Path:
        path = self.log_dir / name
        path.write_text(text or "", encoding="utf-8")
        return path

    def _failed_tests_path(self) -> Path:
        return self.log_dir / "failed-tests.txt"

    def _write_failed_tests_summary(
        self,
        *,
        suite: str,
        phase: str,
        stdout: str,
        extra: str = "",
    ) -> Path:
        """FR #6586: rewrite failed-tests.txt after each suite/rerun (not only at end)."""
        path = self._failed_tests_path()
        nodeids = sorted(parse_pytest_failed_nodeids(stdout or ""))
        lines = [
            f"# failed-tests summary (FR #6586) updated={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            f"# suite={suite} phase={phase}",
        ]
        if extra:
            lines.append(f"# note={extra}")
        if nodeids:
            lines.append(f"# count={len(nodeids)}")
            lines.extend(nodeids)
        else:
            lines.append("# count=0")
            lines.append("(no FAILED/ERROR nodeids parsed)")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _print_progress(self, msg: str) -> None:
        """FR #6586: line to stdout so chair ``*.runner.log`` grows during the run.

        Distinct from ``_progress()`` (FR #6585 BuildProgressPoster accessor).
        """
        print(f"build: {msg}", flush=True)

    def _zip_logs(self) -> Path:
        import zipfile

        zip_path = self.work_dir / f"build-logs-{self.version}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if self.log_dir.is_dir():
                for f in sorted(self.log_dir.rglob("*")):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(self.log_dir)))
        return zip_path

    def _suite_cwd(self, suite: SuiteSpec, *, baseline: bool = False) -> str:
        base = self.repo_root
        if baseline and self.baseline_root is not None:
            base = self.baseline_root
        if suite.cwd in (".", "", None):
            return str(base)
        return str(base / suite.cwd)

    def run(self, *, dry_run: bool = False) -> BuildReport:
        report = BuildReport(ok=False)
        if not is_recipe_build_machine(self.recipe.machine, self.local_machine):
            report.errors.append(
                f"not recipe machine recipe={self.recipe.machine} local={self.local_machine}"
            )
            report.announce_lines.append(
                f"BUILD fail {self.repo} version={self.version}: wrong machine"
                f"{self._id_suffix()}"
            )
            return report
        if dry_run:
            report.ok = True
            report.announce_lines.extend(
                dry_run_plan(
                    self.recipe, repo=self.repo, version=self.version, ref=self.ref
                )
            )
            return report

        self._ensure_dirs()
        baseline = self._resolve_baseline()
        blocking = False
        out_dir = self.work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        assets: list = []
        prog = self._progress()
        if prog is not None:
            with contextlib.suppress(Exception):
                prog.step_start("suites")

        for suite in self.recipe.suites:
            try:
                self._prog_heartbeat()
                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.step_start(f"suite {suite.name} ref")
                rendered_cmd = render_template(
                    suite.cmd,
                    version=self.version,
                    out_dir=str(out_dir),
                    ref=self.ref,
                )
                ref_log = self.log_dir / f"{suite.name}-ref.log"
                self._print_progress(f"suite {suite.name} ref start log={ref_log.name}")
                ref_res = self.run_command_fn(
                    rendered_cmd,
                    cwd=self._suite_cwd(suite),
                    env=dict(suite.env or {}),
                    timeout=float(suite.timeout),
                    name=suite.name,
                    ref_or_baseline=self.ref,
                    log_path=ref_log,
                )
                report.suite_results.append(ref_res)
                # Final rewrite keeps a complete buffer if the stream closed early.
                self._write_log(f"{suite.name}-ref.log", ref_res.stdout)
                self._write_failed_tests_summary(
                    suite=suite.name, phase="ref", stdout=ref_res.stdout
                )
                self._print_progress(
                    f"suite {suite.name} ref done rc={ref_res.exit_code} "
                    f"timed_out={ref_res.timed_out} s={ref_res.duration_s:.1f}"
                )
                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.suite_counts(
                            suite.name, at=str(self.ref), stdout=ref_res.stdout
                        )
                        prog.step_end(
                            f"suite {suite.name} ref",
                            ok=(int(ref_res.exit_code) == 0 and not ref_res.timed_out),
                        )
                if ref_res.timed_out:
                    failure = classify_step_failure(f"suite:{suite.name}:timeout")
                    filed = file_blocker_or_dedupe(
                        self.filer,
                        repo=self.repo,
                        version=self.version,
                        ref=self.ref,
                        failure=failure,
                        log_excerpt=ref_res.stdout[-1500:],
                    )
                    report.blockers_filed.append(filed)
                    blocking = True
                    continue

                # FR #6490: command-not-found is an environment failure — fail the
                # build clearly and do not classify as regression or file blockers.
                if is_command_not_found(ref_res.stdout, ref_res.exit_code):
                    msg = (
                        f"environment failure: suite {suite.name} command could not start "
                        f"(exit {ref_res.exit_code}); missing interpreter/tool on PATH "
                        f"(set BOBIVERSE_PYTHON for the runner service)"
                    )
                    report.errors.append(msg)
                    report.announce_lines.append(
                        f"BUILD fail {self.repo} version={self.version}: {msg}"
                    )
                    blocking = True
                    break

                ref_failed = int(ref_res.exit_code) != 0

                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.step_start(f"suite {suite.name} baseline")
                base_cmd = render_template(
                    suite.cmd,
                    version=self.version,
                    out_dir=str(out_dir),
                    ref=baseline,
                )
                base_log = self.log_dir / f"{suite.name}-baseline.log"
                self._print_progress(f"suite {suite.name} baseline start log={base_log.name}")
                base_res = self.run_command_fn(
                    base_cmd,
                    cwd=self._suite_cwd(suite, baseline=True),
                    env=dict(suite.env or {}),
                    timeout=float(suite.timeout),
                    name=suite.name,
                    ref_or_baseline=baseline,
                    log_path=base_log,
                )
                report.suite_results.append(base_res)
                self._write_log(f"{suite.name}-baseline.log", base_res.stdout)
                self._write_failed_tests_summary(
                    suite=suite.name, phase="baseline", stdout=base_res.stdout
                )
                self._print_progress(
                    f"suite {suite.name} baseline done rc={base_res.exit_code} "
                    f"timed_out={base_res.timed_out} s={base_res.duration_s:.1f}"
                )
                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.suite_counts(
                            suite.name, at=str(baseline), stdout=base_res.stdout
                        )
                        prog.step_end(
                            f"suite {suite.name} baseline",
                            ok=(int(base_res.exit_code) == 0 and not base_res.timed_out),
                        )
                if base_res.timed_out:
                    failure = classify_step_failure(f"suite:{suite.name}:baseline-timeout")
                    filed = file_blocker_or_dedupe(
                        self.filer,
                        repo=self.repo,
                        version=self.version,
                        ref=baseline,
                        failure=failure,
                        log_excerpt=base_res.stdout[-1500:],
                    )
                    report.blockers_filed.append(filed)
                    blocking = True
                baseline_failed = int(base_res.exit_code) != 0 or base_res.timed_out

                # FR #5121: classify by failing nodeid set difference, not suite exit alone.
                # While baseline is red, suite-level compare used to mark every new failure
                # pre_existing. Diff FAILED/ERROR nodeids; only identical sets are pre_existing.
                if ref_failed and not ref_res.timed_out:
                    new_ids = sorted(new_failing_nodeids(ref_res.stdout, base_res.stdout))
                    if not new_ids:
                        ref_ids = parse_pytest_failed_nodeids(ref_res.stdout)
                        if not ref_ids:
                            # Fail closed: red suite with unparseable output.
                            failure = classify_failure(
                                suite.name,
                                ref_failed=True,
                                baseline_failed=False,
                                solo_passed=False,
                            )
                            filed = file_blocker_or_dedupe(
                                self.filer,
                                repo=self.repo,
                                version=self.version,
                                ref=self.ref,
                                failure=failure,
                                log_excerpt=ref_res.stdout[-1500:],
                            )
                            report.blockers_filed.append(filed)
                            blocking = True
                        # else: identical failing set vs baseline → pre_existing, do not block
                    else:
                        total_reruns = len(new_ids)
                        for idx, tid in enumerate(new_ids, start=1):
                            self._prog_heartbeat()
                            solo_cmd = append_pytest_nodeid(rendered_cmd, tid)
                            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tid)[:80]
                            solo_log = self.log_dir / f"{suite.name}-solo-{safe}.log"
                            self._print_progress(
                                f"suite {suite.name} solo start nodeid={tid} log={solo_log.name}"
                            )
                            solo = self.run_command_fn(
                                solo_cmd,
                                cwd=self._suite_cwd(suite),
                                env=dict(suite.env or {}),
                                timeout=float(suite.timeout),
                                name=suite.name,
                                ref_or_baseline=f"{self.ref}-solo",
                                log_path=solo_log,
                            )
                            report.suite_results.append(solo)
                            self._write_log(f"{suite.name}-solo-{safe}.log", solo.stdout)
                            self._write_failed_tests_summary(
                                suite=suite.name,
                                phase=f"solo:{tid}",
                                stdout=solo.stdout or ref_res.stdout,
                                extra=f"solo_rc={solo.exit_code}",
                            )
                            self._print_progress(
                                f"suite {suite.name} solo done nodeid={tid} rc={solo.exit_code}"
                            )
                            if prog is not None:
                                with contextlib.suppress(Exception):
                                    result = (
                                        "timeout"
                                        if solo.timed_out
                                        else ("pass" if int(solo.exit_code) == 0 else "fail")
                                    )
                                    prog.rerun_progress(
                                        index=idx,
                                        total=total_reruns,
                                        nodeid=tid,
                                        result=result,
                                    )
                            if solo.timed_out:
                                failure = classify_step_failure(
                                    f"suite:{suite.name}:solo-timeout:{tid}"
                                )
                                filed = file_blocker_or_dedupe(
                                    self.filer,
                                    repo=self.repo,
                                    version=self.version,
                                    ref=self.ref,
                                    failure=failure,
                                    log_excerpt=solo.stdout[-1500:],
                                )
                                report.blockers_filed.append(filed)
                                blocking = True
                                continue
                            solo_passed = int(solo.exit_code) == 0
                            # New vs baseline by set diff ⇒ baseline_failed=False for this id.
                            failure = classify_failure(
                                tid,
                                ref_failed=True,
                                baseline_failed=False,
                                solo_passed=solo_passed,
                            )
                            if failure.kind in ("new_regression", "step_failure"):
                                filed = file_blocker_or_dedupe(
                                    self.filer,
                                    repo=self.repo,
                                    version=self.version,
                                    ref=self.ref,
                                    failure=failure,
                                    log_excerpt=ref_res.stdout[-1500:],
                                )
                                report.blockers_filed.append(filed)
                                blocking = True
            except Exception as exc:
                # FR #4316: LiveStateTouched / unexpected runner aborts must auto-file
                # (suite regressions already file above; guard raises never reached that path).
                filed = file_runner_abort_blocker(
                    self.filer,
                    repo=self.repo,
                    version=self.version,
                    ref=self.ref,
                    exc=exc,
                    suite_name=suite.name,
                )
                report.blockers_filed.append(filed)
                report.errors.append(f"{type(exc).__name__}: {exc}")
                blocking = True
                break

        if prog is not None:
            with contextlib.suppress(Exception):
                prog.step_end("suites", ok=(not blocking))

        if blocking:
            report.errors.append("blockers present; skipping pack/release")
            report.pack_ok = False
            report.release_ok = False
        else:
            try:
                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.step_start("pack")
                pack_cmd = str((self.recipe.pack or {}).get("cmd") or "")
                rendered_pack = render_template(
                    pack_cmd,
                    version=self.version,
                    out_dir=str(out_dir),
                    ref=self.ref,
                )
                if self.pack_fn is not None:
                    assets = self.pack_fn(
                        version=self.version,
                        out_dir=out_dir,
                        cmd=rendered_pack,
                        recipe=self.recipe,
                    )
                    report.pack_ok = True
                elif pack_cmd:
                    pack_res = self.run_command_fn(
                        rendered_pack,
                        cwd=str(self.repo_root),
                        env={},
                        timeout=3600.0,
                        name="pack",
                        ref_or_baseline=self.ref,
                    )
                    report.suite_results.append(pack_res)
                    self._write_log("pack.log", pack_res.stdout)
                    if pack_res.timed_out or int(pack_res.exit_code) != 0:
                        failure = classify_step_failure("pack")
                        filed = file_blocker_or_dedupe(
                            self.filer,
                            repo=self.repo,
                            version=self.version,
                            ref=self.ref,
                            failure=failure,
                            log_excerpt=pack_res.stdout[-1500:],
                        )
                        report.blockers_filed.append(filed)
                        report.pack_ok = False
                        blocking = True
                    else:
                        missing = []
                        for art in (self.recipe.pack or {}).get("artifacts") or []:
                            aname = render_template(
                                str(art),
                                version=self.version,
                                out_dir=str(out_dir),
                                ref=self.ref,
                            )
                            if not (out_dir / aname).is_file():
                                missing.append(aname)
                        if missing:
                            failure = classify_step_failure("pack:artifacts")
                            filed = file_blocker_or_dedupe(
                                self.filer,
                                repo=self.repo,
                                version=self.version,
                                ref=self.ref,
                                failure=failure,
                                log_excerpt="missing: " + ", ".join(missing),
                            )
                            report.blockers_filed.append(filed)
                            report.pack_ok = False
                            blocking = True
                        else:
                            report.pack_ok = True
                            assets = [
                                out_dir
                                / render_template(
                                    str(a),
                                    version=self.version,
                                    out_dir=str(out_dir),
                                    ref=self.ref,
                                )
                                for a in ((self.recipe.pack or {}).get("artifacts") or [])
                            ]
                else:
                    report.pack_ok = True
                    assets = []

                assert_cmd = str((self.recipe.pack or {}).get("assert") or "")
                defer_assert = (
                    self.release_fn is not None
                    and str((self.recipe.release or {}).get("target") or "") == "github-prerelease"
                )
                if report.pack_ok and assert_cmd and self.pack_fn is None and not defer_assert:
                    assert_rendered = render_template(
                        assert_cmd,
                        version=self.version,
                        out_dir=str(out_dir),
                        ref=self.ref,
                    )
                    assert_res = self.run_command_fn(
                        assert_rendered,
                        cwd=str(self.repo_root),
                        env={},
                        timeout=1800.0,
                        name="assert",
                        ref_or_baseline=self.ref,
                    )
                    report.suite_results.append(assert_res)
                    self._write_log("assert.log", assert_res.stdout)
                    if assert_res.timed_out or int(assert_res.exit_code) != 0:
                        failure = classify_step_failure("assert")
                        filed = file_blocker_or_dedupe(
                            self.filer,
                            repo=self.repo,
                            version=self.version,
                            ref=self.ref,
                            failure=failure,
                            log_excerpt=assert_res.stdout[-1500:],
                        )
                        report.blockers_filed.append(filed)
                        report.pack_ok = False
                        blocking = True
            except Exception as exc:
                # FR #4316: pack-step LiveStateTouched / unexpected abort must auto-file.
                report.errors.append(f"pack: {type(exc).__name__}: {exc}")
                filed = file_runner_abort_blocker(
                    self.filer,
                    repo=self.repo,
                    version=self.version,
                    ref=self.ref,
                    exc=exc,
                    suite_name="pack",
                )
                report.blockers_filed.append(filed)
                report.pack_ok = False
                blocking = True
                assets = []
            if prog is not None:
                with contextlib.suppress(Exception):
                    prog.step_end("pack", ok=bool(report.pack_ok) and not blocking)

            rel = self.recipe.release or {}
            never_latest = bool(rel.get("never_latest"))
            target = str(rel.get("target") or "")
            tag = render_template(
                str(rel.get("tag") or "v{{version}}"),
                version=self.version,
                out_dir=str(out_dir),
                ref=self.ref,
            )
            if not blocking and report.pack_ok and target == "github-prerelease":
                try:
                    if prog is not None:
                        with contextlib.suppress(Exception):
                            prog.step_start("release")
                    if self.release_fn is not None:
                        self.release_fn(
                            tag=tag,
                            assets=assets,
                            prerelease=True,
                            latest=(False if never_latest else None),
                        )
                        report.release_ok = True
                        post_assert = str((self.recipe.pack or {}).get("assert") or "")
                        if post_assert and self.pack_fn is None:
                            pa = self.run_command_fn(
                                render_template(
                                    post_assert,
                                    version=self.version,
                                    out_dir=str(out_dir),
                                    ref=self.ref,
                                ),
                                cwd=str(self.repo_root),
                                env={},
                                timeout=1800.0,
                                name="assert",
                                ref_or_baseline=self.ref,
                            )
                            report.suite_results.append(pa)
                            self._write_log("assert.log", pa.stdout)
                            if pa.timed_out or int(pa.exit_code) != 0:
                                raise RuntimeError(
                                    "Assert-BobiverseReleaseAssets failed: "
                                    + (pa.stdout or "")[-800:]
                                )
                    else:
                        report.release_ok = False
                        report.errors.append("release_fn not provided")
                except Exception as exc:
                    report.errors.append(f"release: {type(exc).__name__}: {exc}")
                    failure = classify_step_failure("release")
                    filed = file_blocker_or_dedupe(
                        self.filer,
                        repo=self.repo,
                        version=self.version,
                        ref=self.ref,
                        failure=failure,
                        log_excerpt=str(exc),
                    )
                    report.blockers_filed.append(filed)
                    report.release_ok = False
                    blocking = True
                if prog is not None:
                    with contextlib.suppress(Exception):
                        prog.step_end("release", ok=bool(report.release_ok))
            elif not blocking and report.pack_ok and not target:
                report.release_ok = True

        try:
            zip_path = self._zip_logs()
            report.log_zip = str(zip_path)
        except Exception as exc:
            report.errors.append(f"log_zip: {type(exc).__name__}: {exc}")

        has_release_target = bool((self.recipe.release or {}).get("target"))
        report.ok = (
            (not blocking)
            and report.pack_ok
            and (report.release_ok or not has_release_target)
        )
        tag_s = render_template(
            str((self.recipe.release or {}).get("tag") or "v{{version}}"),
            version=self.version,
        )
        if report.ok:
            report.announce_lines.append(
                f"BUILD ok {self.repo} version={self.version} ref={self.ref} "
                f"tag={tag_s} prerelease "
                f"never_latest={bool((self.recipe.release or {}).get('never_latest'))}"
                f"{self._id_suffix()}"
            )
        else:
            n = len(report.blockers_filed)
            urls = [
                str(b.get("url") or "").strip()
                for b in report.blockers_filed
                if str(b.get("url") or "").strip()
            ]
            url_bit = (" blocker=" + " ".join(urls)) if urls else ""
            report.announce_lines.append(
                f"BUILD fail {self.repo} version={self.version} ref={self.ref} "
                f"blockers={n} pack={report.pack_ok} release={report.release_ok}"
                f"{url_bit}{self._id_suffix()}"
            )
        return report


def enqueue_build_job(
    route: dict,
    *,
    queue_dir: Path | str,
    local_machine: str,
    recipe_machine: str = "",
) -> Path:
    """Write a BUILD v1 job JSON under ``queue_dir`` (home/build-queue or ProgramData)."""
    q = Path(queue_dir)
    q.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    ver = str(route.get("version") or "unknown")
    path = q / f"build-{ver}-{ts}.json"
    payload = {
        "v": 1,
        "kind": "BUILD",
        "repos": list(route.get("repos") or []),
        "version": ver,
        "ref": route.get("ref") or "HEAD",
        "id": str(route.get("id") or "").strip(),
        "local_machine": local_machine,
        "recipe_machine": recipe_machine,
        "queued_at": ts,
        "status": "queued",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def default_build_route_marker_dir() -> Path:
    """FR #5266: machine-global BUILD v1 route claims (chair + ear share this)."""
    return Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Bobiverse" / "build-routes"


def default_machine_build_lock_path() -> Path:
    """FR #5266: one BuildLock file per machine, not per home."""
    return Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Bobiverse" / "build-locks.json"


def build_route_id(route: dict) -> str:
    rid = str(route.get("id") or "").strip()
    if rid:
        return rid
    raw = str(route.get("raw") or "")
    return "h-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _sanitize_build_route_id(route_id: str) -> str:
    rid = "".join(
        ch if ch.isalnum() or ch in "-._" else "_" for ch in str(route_id or "").strip()
    )
    return rid or "unknown"


class _ClaimOutcome(NamedTuple):
    """FR #6558: private claim result (public APIs stay bool)."""

    status: str  # claimed | duplicate | reclaimed | error
    path: Path
    age_s: float | None
    error: str = ""


def _build_route_marker_age_s(path: Path, *, now: float | None = None) -> float | None:
    """Age of a ``.claimed`` marker: content integer timestamp, else st_mtime.

    Negative ages clamp to 0. Unreadable content + missing mtime -> None (fail closed).
    """
    clock = float(now if now is not None else time.time())
    content_ts: float | None = None
    try:
        text = path.read_text(encoding="ascii", errors="ignore").strip()
        if text:
            # first token must be an integer unix timestamp
            token = text.split()[0]
            content_ts = float(int(token))
    except (OSError, ValueError, IndexError):
        content_ts = None
    if content_ts is not None:
        return max(0.0, clock - content_ts)
    try:
        return max(0.0, clock - float(path.stat().st_mtime))
    except OSError:
        return None


def _try_advisory_reclaim_lock(fh, timeout_s: float = 0.5) -> bool:
    """Non-blocking reclaim lock with short retry (msvcrt / fcntl)."""
    deadline = time.monotonic() + max(0.05, float(timeout_s))
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)


def _unlock_advisory_reclaim(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _reclaim_stale_build_route_marker(
    path: Path,
    *,
    stale_after_s: float,
    first_age_s: float | None,
) -> _ClaimOutcome:
    """Replace an expired id-less marker under a stable never-unlinked reclaim lock."""
    if first_age_s is None:
        return _ClaimOutcome("duplicate", path, None, "age=unknown")
    if first_age_s <= float(stale_after_s):
        return _ClaimOutcome("duplicate", path, first_age_s)

    lock_path = path.parent / ".reclaim.lock"
    try:
        # Never unlink; create once so the lock path stays stable across reclaimers.
        fd_lock = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    except OSError as exc:
        return _ClaimOutcome("error", path, first_age_s, f"reclaim-lock-open: {exc}")
    fh = None
    tmp: Path | None = None
    try:
        fh = os.fdopen(fd_lock, "r+b", closefd=True)
        fd_lock = -1  # owned by fh
        if not _try_advisory_reclaim_lock(fh, timeout_s=0.5):
            return _ClaimOutcome("error", path, first_age_s, "reclaim-lock-timeout")
        age2 = _build_route_marker_age_s(path)
        if age2 is None:
            return _ClaimOutcome("duplicate", path, None, "age=unknown")
        if age2 <= float(stale_after_s):
            return _ClaimOutcome("duplicate", path, age2)
        now_i = int(time.time())
        tmp = path.parent / f".{path.name}.{os.getpid()}.{now_i}.tmp"
        tmp.write_text(f"{now_i}\n", encoding="ascii")
        os.replace(str(tmp), str(path))
        tmp = None
        return _ClaimOutcome("reclaimed", path, age2)
    except OSError as exc:
        return _ClaimOutcome("error", path, first_age_s, f"reclaim-replace: {exc}")
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
        if fh is not None:
            _unlock_advisory_reclaim(fh)
            try:
                fh.close()
            except OSError:
                pass
        elif fd_lock >= 0:
            try:
                os.close(fd_lock)
            except OSError:
                pass


def _claim_build_route_marker_detail(
    marker_dir: Path | str,
    route_id: str,
    *,
    stale_after_s: float | None = None,
) -> _ClaimOutcome:
    """O_EXCL claim with optional id-less stale reclaim (FR #6558)."""
    rid = _sanitize_build_route_id(route_id)
    d = Path(marker_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rid}.claimed"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError:
        age = _build_route_marker_age_s(path)
        ttl = float(stale_after_s) if stale_after_s is not None else None
        if ttl is not None and ttl > 0 and age is not None and age > ttl:
            return _reclaim_stale_build_route_marker(
                path, stale_after_s=ttl, first_age_s=age
            )
        return _ClaimOutcome("duplicate", path, age)
    except OSError as exc:
        return _ClaimOutcome("error", path, None, str(exc))
    try:
        os.write(fd, f"{int(time.time())}\n".encode("ascii"))
    finally:
        os.close(fd)
    return _ClaimOutcome("claimed", path, 0.0)


def claim_build_route_marker(
    marker_dir: Path | str,
    route_id: str,
    *,
    stale_after_s: float | None = None,
) -> bool:
    """O_EXCL claim. First caller True; later callers on the same id False.

    FR #6558: optional ``stale_after_s`` reclaims an expired marker (strictly older
    than the threshold). Default ``None`` keeps permanent exclusion (FR #5266).
    """
    outcome = _claim_build_route_marker_detail(
        marker_dir, route_id, stale_after_s=stale_after_s
    )
    return outcome.status in ("claimed", "reclaimed")


def consume_build_v1(
    line: str,
    local_machine: str,
    recipe_machine: str,
    *,
    queue_dir: Path | str | None = None,
    route_marker_dir: Path | str | None = None,
    stale_claim_s: float | None = None,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Return True when this host should accept the BUILD v1 route (optionally enqueue).

    Does not pack/release in-process; writes a job JSON when ``queue_dir`` is set.
    FR #5266: when ``route_marker_dir`` is set, the first caller on this machine
    claims the route id with O_EXCL; later chair/ear copies return False.
    FR #6558: id-less routes may reclaim a marker older than ``stale_claim_s``;
    explicit ``id=`` claims stay permanent. Duplicate / error / reclaim each emit
    one log line when ``log`` is set.
    """
    route = parse_build_v1_route(line)
    if not route:
        return False
    if not is_recipe_build_machine(recipe_machine, local_machine):
        return False
    if route_marker_dir is not None:
        rid = build_route_id(route)
        explicit_id = bool(str(route.get("id") or "").strip())
        stale = None if explicit_id else stale_claim_s
        outcome = _claim_build_route_marker_detail(
            route_marker_dir, rid, stale_after_s=stale
        )
        if outcome.status == "duplicate":
            if log is not None:
                age_txt = (
                    "unknown"
                    if outcome.age_s is None
                    else f"{outcome.age_s:.0f}"
                )
                thr = "never" if stale is None else f"{float(stale):.0f}"
                log(
                    f"BUILD v1 route dropped as duplicate id={rid} "
                    f"marker={outcome.path} age={age_txt}s stale_after={thr}"
                )
            return False
        if outcome.status == "error":
            if log is not None:
                log(
                    f"BUILD v1 route claim error id={rid} "
                    f"marker={outcome.path}: {outcome.error}"
                )
            return False
        if outcome.status == "reclaimed" and log is not None:
            prev = (
                "unknown"
                if outcome.age_s is None
                else f"{outcome.age_s:.0f}"
            )
            log(
                f"BUILD v1 route claim reclaimed id={rid} "
                f"marker={outcome.path} previous_age={prev}s"
            )
    if queue_dir is not None:
        enqueue_build_job(
            route,
            queue_dir=queue_dir,
            local_machine=local_machine,
            recipe_machine=recipe_machine,
        )
    return True

# ------------------------------------------------------------------ !installtest (FR #4026 WP3)


def parse_installtest_v1_route(text: str) -> dict | None:
    """Parse ``INSTALLTEST v1 repo=owner/name version=X tag=Y`` -> dict or None."""
    raw = (text or "").strip()
    if raw.startswith(":"):
        raw = raw[1:].strip()
    m = INSTALLTEST_V1_RE.match(raw)
    if not m:
        return None
    return {
        "repo": m.group("repo"),
        "version": m.group("version"),
        "tag": m.group("tag"),
        "raw": raw,
    }


def enqueue_installtest_job(
    route: dict,
    *,
    queue_dir: Path | str,
    local_machine: str,
    recipe_machine: str = "",
) -> Path:
    """Write an INSTALLTEST v1 job JSON under ``queue_dir`` (home/build-queue)."""
    q = Path(queue_dir)
    q.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    ver = str(route.get("version") or "unknown")
    path = q / f"installtest-{ver}-{ts}.json"
    payload = {
        "v": 1,
        "kind": "INSTALLTEST",
        "repo": route.get("repo") or "",
        "version": ver,
        "tag": route.get("tag") or f"v{ver}",
        "local_machine": local_machine,
        "recipe_machine": recipe_machine,
        "queued_at": ts,
        "status": "queued",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def consume_installtest_v1(
    line: str,
    local_machine: str,
    recipe_machine: str,
    *,
    queue_dir: Path | str | None = None,
) -> bool:
    """Return True when this host should accept the INSTALLTEST v1 route (optionally enqueue).

    Does not msiexec in-process; writes a job JSON when ``queue_dir`` is set.
    """
    route = parse_installtest_v1_route(line)
    if not route:
        return False
    if not is_recipe_build_machine(recipe_machine, local_machine):
        return False
    if queue_dir is not None:
        enqueue_installtest_job(
            route,
            queue_dir=queue_dir,
            local_machine=local_machine,
            recipe_machine=recipe_machine,
        )
    return True


@dataclass
class InstallTestDecision:
    ok: bool
    reason: str = ""
    pm_lines: list = field(default_factory=list)
    repo: str = ""
    version: str = ""
    tag: str = ""
    dry_run: bool = False
    route: str = ""
    machine: str = ""
def parse_installtest(body: str) -> tuple[str, str] | None:
    """Return (subcmd, rest) for ``!installtest``, or None if not that command.
    subcmd is ``run`` | ``dry-run`` | ``\"\"`` (bare / usage).
    """
    text = (body or "").strip()
    if not text.lower().startswith("!installtest"):
        return None
    parts = text.split(None, 2)
    if len(parts) == 1:
        return "", ""
    sub = parts[1].lower()
    rest = parts[2] if len(parts) > 2 else ""
    if sub in ("dry-run", "dryrun", "dry"):
        return "dry-run", rest
    # !installtest <owner/repo> <version> [tag]
    return "run", text[len("!installtest") :].strip()
def decide_installtest(
    *,
    who,
    body: str,
    may: Callable,
    denied_line: Callable,
    recipe_loader: Callable[[str], BuildRecipe | None],
    local_machine: str = "",
    ignored: Iterable[str] = (),
) -> InstallTestDecision | None:
    parsed = parse_installtest(body)
    if parsed is None:
        return None
    sub, rest = parsed
    if not may("installtest", who):
        return InstallTestDecision(False, "denied", [denied_line("installtest")])
    dry = sub == "dry-run"
    arg = rest if dry else (rest if sub == "run" else "")
    if sub == "" or (dry and not arg) or (not dry and not arg):
        return InstallTestDecision(
            False,
            "usage",
            [
                "installtest: usage !installtest <owner/repo> <version> [tag]",
                "installtest: also !installtest dry-run <owner/repo> <version> [tag]",
            ],
            dry_run=dry,
        )
    tokens = arg.split()
    if len(tokens) < 2:
        return InstallTestDecision(
            False,
            "usage",
            ["installtest: usage !installtest <owner/repo> <version> [tag]"],
            dry_run=dry,
        )
    repo = tokens[0].strip()
    if not REPO_RE.match(repo):
        return InstallTestDecision(False, "bad_repo", [f"installtest: bad repo id: {repo}"], dry_run=dry)
    if normalize_repo(repo) in {normalize_repo(x) for x in ignored}:
        return InstallTestDecision(
            False, "ignored", [f"installtest: {repo} is ignored; nothing started"], repo=repo, dry_run=dry
        )
    version = tokens[1]
    tag = tokens[2] if len(tokens) > 2 else f"v{version}"
    try:
        recipe = recipe_loader(repo)
    except RecipeError as exc:
        msg = str(exc) if str(exc).startswith("build:") else f"installtest: {repo} {exc}"
        # normalise prefix for installtest context
        if msg.startswith("build:"):
            msg = "installtest:" + msg[len("build:") :]
        return InstallTestDecision(False, "no_recipe", [msg], repo=repo, version=version, tag=tag, dry_run=dry)
    if recipe is None:
        return InstallTestDecision(
            False,
            "no_recipe",
            [f"installtest: {repo} has no .bobiverse/build.yml; nothing started"],
            repo=repo,
            version=version,
            tag=tag,
            dry_run=dry,
        )
    if not recipe.install_test:
        return InstallTestDecision(
            False,
            "no_install_test",
            [f"installtest: {repo} recipe has no install_test; nothing started"],
            repo=repo,
            version=version,
            tag=tag,
            dry_run=dry,
        )
    it = recipe.install_test
    target_machine = str(it.get("machine") or recipe.machine or "").strip()
    if local_machine and not is_recipe_build_machine(target_machine, local_machine):
        return InstallTestDecision(
            False,
            "wrong_machine",
            [
                f"installtest: {repo} requires machine={target_machine} "
                f"(folded={fold_build_machine(target_machine)}); local={local_machine}"
            ],
            repo=repo,
            version=version,
            tag=tag,
            dry_run=dry,
            machine=target_machine,
        )
    products = list(it.get("products") or ["jeeves", "bob", "airc"])
    if dry:
        lines = [
            f"installtest dry-run: {repo} version={version} tag={tag} "
            f"machine={target_machine} products={','.join(products)}",
            "installtest dry-run: would msiexec /i /qn /l*v each MSI, post-check "
            "service/SASL/channels/seat ACK, file release-blocker on fail; nothing installed",
        ]
        return InstallTestDecision(
            True, "dry_run", lines, repo=repo, version=version, tag=tag, dry_run=True, machine=target_machine
        )
    route = f"INSTALLTEST v1 repo={repo} version={version} tag={tag}"
    lines = [
        f"installtest: queued {repo} version={version} tag={tag} machine={target_machine} "
        f"products={','.join(products)}"
    ]
    return InstallTestDecision(
        True, "ok", lines, repo=repo, version=version, tag=tag, dry_run=False, route=route, machine=target_machine
    )
@dataclass
class InstallTestReport:
    ok: bool
    steps: list = field(default_factory=list)
    evidence_dir: str = ""
    blockers_filed: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    announce_lines: list = field(default_factory=list)
    dry_run: bool = False
def default_msiexec_fn(msi_path: Path, log_path: Path, *, extra: str = "") -> int:
    """Real msiexec /i /qn /l*v (tests inject a stub)."""
    cmd = ["msiexec", "/i", str(msi_path), "/qn", "/l*v", str(log_path)]
    for tok in (extra or "").split():
        if tok:
            cmd.append(tok)
    return int(subprocess.call(cmd))
def default_asset_resolver(version: str, tag: str, *, products: list[str] | None = None) -> list[Path]:
    """Look under ProgramData/Bobiverse/build-work and a releases cache for product MSIs."""
    products = list(products or ["jeeves", "bob", "airc"])
    roots = [
        Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "Bobiverse" / "build-work",
        Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "Bobiverse" / "releases",
        Path(os.environ.get("LOCALAPPDATA") or "") / "Bobiverse" / "build-work",
    ]
    found: list[Path] = []
    for product in products:
        name = f"{product}-{version}.msi"
        hit: Path | None = None
        for root in roots:
            if not root:
                continue
            cand = root / name
            if cand.is_file():
                hit = cand
                break
            # also search one level of version/tag dirs
            for sub in (root / tag, root / version, root / f"v{version}"):
                c2 = sub / name
                if c2.is_file():
                    hit = c2
                    break
            if hit:
                break
        if hit:
            found.append(hit)
    return found
def zip_evidence_dir(evidence_dir: Path, *, version: str) -> Path | None:
    evidence_dir = Path(evidence_dir)
    if not evidence_dir.is_dir():
        return None
    zip_path = evidence_dir.parent / f"installtest-{version}-evidence.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(evidence_dir.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(evidence_dir)))
    return zip_path
class InstallTestRunner:
    """Install pre-release MSIs and post-check (FR #4026). All side effects injectable."""
    def __init__(
        self,
        *,
        repo: str,
        version: str,
        tag: str = "",
        recipe: BuildRecipe,
        evidence_dir: Path | str,
        msiexec_fn: Callable[..., int] | None = None,
        postcheck_fn: Callable[[str], dict] | None = None,
        filer: Any = None,
        asset_resolver: Callable[..., list[Path]] | None = None,
        open_issues: Iterable[dict] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.repo = repo
        self.version = version
        self.tag = tag or f"v{version}"
        self.recipe = recipe
        self.evidence_dir = Path(evidence_dir)
        self.msiexec_fn = msiexec_fn
        self.postcheck_fn = postcheck_fn
        self.filer = filer
        self.asset_resolver = asset_resolver
        self.open_issues = list(open_issues) if open_issues is not None else None
        self.dry_run = dry_run
    def _products(self) -> list[str]:
        it = self.recipe.install_test or {}
        return list(it.get("products") or ["jeeves", "bob", "airc"])
    def _msiexec_extra(self) -> str:
        it = self.recipe.install_test or {}
        return str(it.get("msiexec_extra") or "").strip()
    def _resolve_assets(self) -> list[Path]:
        products = self._products()
        if self.asset_resolver is not None:
            try:
                return list(self.asset_resolver(self.version, self.tag))
            except TypeError:
                return list(self.asset_resolver(self.version, self.tag, products=products))
        return default_asset_resolver(self.version, self.tag, products=products)
    def _file_blocker(self, step: str, excerpt: str) -> dict | None:
        if self.filer is None:
            return None
        failure = classify_step_failure(step)
        # Reuse WP2 file_blocker_or_dedupe (FakeGitHubFiler / GitHubFiler).
        return file_blocker_or_dedupe(
            self.filer,
            repo=self.repo,
            version=self.version,
            ref=self.tag,
            failure=failure,
            log_excerpt=excerpt,
            build_url="",
        )
    def run(self) -> InstallTestReport:
        steps: list[str] = []
        errors: list[str] = []
        blockers: list[dict] = []
        announce: list[str] = []
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        products = self._products()
        if self.dry_run:
            plan = [
                f"resolve MSIs for {','.join(products)} version={self.version} tag={self.tag}",
                "msiexec /i /qn /l*v each product",
                "post-check service_up sasl_ok channels_ok seat_ack",
                "file release-blocker (dedupe) on failure; zip evidence",
            ]
            return InstallTestReport(
                True,
                plan,
                str(self.evidence_dir),
                [],
                [],
                [f"installtest dry-run {self.repo} {self.version}"],
                dry_run=True,
            )
        assets = self._resolve_assets()
        if not assets:
            err = f"installtest: no MSI assets for version={self.version} tag={self.tag}"
            errors.append(err)
            steps.append("resolve_assets:fail")
            b = self._file_blocker("resolve_assets", err)
            if b:
                blockers.append(b)
            zip_evidence_dir(self.evidence_dir, version=self.version)
            announce.append(f"installtest FAIL {self.repo} {self.version}: no assets")
            return InstallTestReport(False, steps, str(self.evidence_dir), blockers, errors, announce)
        # Map product -> path by filename prefix
        by_product: dict[str, Path] = {}
        for p in assets:
            stem = p.name.lower()
            for prod in products:
                if stem.startswith(f"{prod.lower()}-") and stem.endswith(".msi"):
                    by_product[prod] = p
                    break
        missing = [prod for prod in products if prod not in by_product]
        if missing:
            err = f"installtest: missing MSI for products={','.join(missing)}"
            errors.append(err)
            steps.append("resolve_assets:missing")
            b = self._file_blocker("resolve_assets", err)
            if b:
                blockers.append(b)
        msiexec = self.msiexec_fn or (
            lambda msi, log: default_msiexec_fn(msi, log, extra=self._msiexec_extra())
        )
        postcheck = self.postcheck_fn or (lambda _product: {
            "service_up": False,
            "sasl_ok": False,
            "channels_ok": False,
            "seat_ack": False,
        })
        all_ok = not missing
        for prod in products:
            msi = by_product.get(prod)
            if msi is None:
                continue
            log_path = self.evidence_dir / f"{prod}-{self.version}-msiexec.log"
            try:
                rc = int(msiexec(msi, log_path))
            except Exception as exc:
                rc = -1
                log_path.write_text(f"msiexec raised {type(exc).__name__}: {exc}\n", encoding="utf-8")
            step_name = f"msiexec:{prod}"
            if rc != 0:
                all_ok = False
                err = f"{step_name} exit={rc}"
                errors.append(err)
                steps.append(f"{step_name}:fail:{rc}")
                excerpt = ""
                try:
                    excerpt = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
                except Exception:
                    excerpt = err
                b = self._file_blocker(step_name, excerpt or err)
                if b:
                    blockers.append(b)
                continue
            steps.append(f"{step_name}:ok")
            try:
                checks = dict(postcheck(prod) or {})
            except Exception as exc:
                all_ok = False
                err = f"postcheck:{prod} raised {type(exc).__name__}: {exc}"
                errors.append(err)
                steps.append(f"postcheck:{prod}:fail")
                b = self._file_blocker(f"postcheck:{prod}", err)
                if b:
                    blockers.append(b)
                continue
            required = ("service_up", "sasl_ok", "channels_ok", "seat_ack")
            failed_keys = [k for k in required if not checks.get(k)]
            (self.evidence_dir / f"{prod}-postcheck.json").write_text(
                json.dumps(checks, indent=2) + "\n", encoding="utf-8"
            )
            if failed_keys:
                all_ok = False
                err = f"postcheck:{prod} failed keys={','.join(failed_keys)}"
                errors.append(err)
                steps.append(f"postcheck:{prod}:fail")
                b = self._file_blocker(f"postcheck:{prod}", err + "\n" + json.dumps(checks))
                if b:
                    blockers.append(b)
            else:
                steps.append(f"postcheck:{prod}:ok")
        zip_evidence_dir(self.evidence_dir, version=self.version)
        if all_ok:
            announce.append(f"installtest PASS {self.repo} {self.version} products={','.join(products)}")
        else:
            announce.append(
                f"installtest FAIL {self.repo} {self.version} blockers={len(blockers)} errors={len(errors)}"
            )
        return InstallTestReport(
            all_ok, steps, str(self.evidence_dir), blockers, errors, announce, dry_run=False
        )


# ------------------------------------------------------------------ live helpers (hotpatch-build)


def fetch_remote_recipe(
    repo: str,
    *,
    ref: str | None = None,
    gh_runner: Callable | None = None,
) -> BuildRecipe | None:
    """Load ``.bobiverse/build.yml`` from GitHub for ``repo``; None when the repo has none.

    Optional *ref* is passed as ``?ref=`` (FR #6484). Empty / ``HEAD`` maps to ``main``.
    """
    import subprocess as _sp
    import tempfile as _tf

    runner = gh_runner or _sp.run
    api = f"repos/{normalize_repo(repo)}/contents/.bobiverse/build.yml"
    ref_s = (ref or "").strip()
    if ref_s and ref_s.upper() != "HEAD":
        api = f"{api}?ref={ref_s}"
    elif ref_s.upper() == "HEAD":
        api = f"{api}?ref=main"
    cp = runner(
        [
            "gh", "api", api,
            "-H", "Accept: application/vnd.github.raw",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    code = int(getattr(cp, "returncode", 0) or 0)
    out = getattr(cp, "stdout", "") or ""
    err = getattr(cp, "stderr", "") or ""
    if code != 0:
        if "404" in (err + out) or "Not Found" in (err + out):
            return None
        raise RecipeError(f"build: {repo} recipe lookup failed rc={code}")
    with _tf.TemporaryDirectory() as td:
        p = Path(td) / ".bobiverse"
        p.mkdir()
        (p / "build.yml").write_text(out, encoding="utf-8")
        return load_recipe(Path(td))


def load_bobiverse_recipe_local_or_remote(
    candidates: list[Path] | tuple[Path, ...],
    repo: str,
    *,
    ref: str | None = None,
    gh_runner: Callable | None = None,
    ensure_token: Callable[[], None] | None = None,
) -> BuildRecipe:
    """Local ``.bobiverse/build.yml`` first; else GitHub fetch (FR #6484 packaged chair).

    FR #6487: a present local file that fails to parse/validate is not treated as
    missing — the real ``RecipeError`` propagates (no silent remote fallback).
    Raises ``RecipeError`` with the familiar ``nothing started`` line when both miss.
    """
    for cand in candidates:
        root = Path(cand)
        if not recipe_path(root).is_file():
            continue
        return load_recipe(root)
    if ensure_token is not None:
        try:
            ensure_token()
        except Exception:
            pass
    recipe = fetch_remote_recipe(repo, ref=ref, gh_runner=gh_runner)
    if recipe is None:
        raise RecipeError(f"build: {repo} has no .bobiverse/build.yml; nothing started")
    return recipe


def make_github_prerelease_fn(
    repo: str,
    *,
    target_sha: str,
    title: str,
    notes: str,
    gh_runner: Callable | None = None,
) -> Callable:
    """release_fn for BuildRunner: ``gh release create --prerelease --latest=false`` + verify."""
    import subprocess as _sp

    runner = gh_runner or _sp.run

    def _gh(args: list[str]) -> str:
        cp = runner(["gh", *args], capture_output=True, text=True, check=False)
        if int(getattr(cp, "returncode", 0) or 0) != 0:
            raise RuntimeError(
                f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed: "
                f"{(getattr(cp, 'stderr', '') or getattr(cp, 'stdout', '') or '')[-500:]}"
            )
        return getattr(cp, "stdout", "") or ""

    def release_fn(*, tag: str, assets, prerelease: bool = True, latest=None) -> dict:
        if not prerelease:
            raise RuntimeError("refusing non-prerelease")
        args = [
            "release", "create", tag, "--repo", normalize_repo(repo),
            "--target", target_sha, "--prerelease", "--latest=false",
            "--title", title, "--notes", notes,
        ]
        args.extend(str(a) for a in (assets or []))
        _gh(args)
        view = json.loads(
            _gh(["release", "view", tag, "--repo", normalize_repo(repo), "--json", "isPrerelease,url"])
            or "{}"
        )
        if not view.get("isPrerelease"):
            raise RuntimeError(f"release {tag} is not a pre-release")
        try:
            latest_tag = _gh(
                ["api", f"repos/{normalize_repo(repo)}/releases/latest", "--jq", ".tag_name"]
            ).strip()
        except RuntimeError:
            latest_tag = ""
        if latest_tag == tag:
            raise RuntimeError(f"release {tag} became Latest")
        return {"tag": tag, "url": view.get("url", "")}

    return release_fn


# ------------------------------------------------------------------ suite isolation (#4183)

LIVE_STATE_FILES = (
    "queue.json", "focus.json", "seat-holds.json", "seat-ledger.json",
    "job-cost-ledger.json",  # FR #6387: measured DONE model/token rows
    "offer-precompute.json", "registered-machines.json",
)
_DEAD_URL = "http://127.0.0.1:9/isolated-build-suite"


def isolated_suite_env(work_dir: Path | str, tag: str) -> dict:
    """Env that points every home/state/URL a suite could touch at a throwaway dir (#4183).

    Suites run on the recipe machine next to the live chair; without this they fell back to
    ``%USERPROFILE%\\.bobiverse`` / ``.jeeves`` and the live report/webhook URLs.
    """
    import socket as _so

    base = Path(work_dir) / "iso" / re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)
    prof = base / "profile"
    dirs = {
        "USERPROFILE": prof,
        "HOME": prof,
        "APPDATA": prof / "AppData" / "Roaming",
        "LOCALAPPDATA": prof / "AppData" / "Local",
        "ProgramData": base / "ProgramData",
        "PROGRAMDATA": base / "ProgramData",
        "ALLUSERSPROFILE": base / "ProgramData",
        "BOB_HOME": prof / ".jeeves",
        "BOB_DIGEST_HOME": prof / ".bobiverse",
        "BOB_CONFIG_DIR": base / "config",
        "TEMP": base / "tmp",
        "TMP": base / "tmp",
    }
    for d in dirs.values():
        Path(d).mkdir(parents=True, exist_ok=True)
    s = _so.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = {k: str(v) for k, v in dirs.items()}
    drive, _, rest = str(prof).partition(":")
    if rest:
        env["HOMEDRIVE"] = drive + ":"
        env["HOMEPATH"] = rest
    env.update({
        "BOB_REPORT_PORT": str(port),
        "BOB_DIGEST_URL": _DEAD_URL,
        "BOB_INTAKE_URL": _DEAD_URL,
        "BOB_HOME_NO_MIGRATE": "1",
        "BOBIVERSE_BUILD_SUITE": "1",
        "GH_TOKEN": "",
        "GITHUB_TOKEN": "",
        "AGENTIC_IRC_PASSWORD": "",
        "BOB_IRC_PASSWORD": "",
    })
    return env


def live_state_fingerprint(homes: Iterable[Path | str]) -> dict:
    """Damage signals only: the live chair rewrites these files all the time, so a hash
    diff is not damage. Track queue row keys and focus repos/items (#4183 / #4408)."""
    out: dict = {}
    for h in homes:
        q = Path(h) / "queue.json"
        try:
            data = json.loads(q.read_text(encoding="utf-8")) if q.is_file() else None
        except Exception:
            data = None
        if isinstance(data, dict):
            keys = set()
            for bucket in ("unaccepted", "accepted", "done"):
                for row in data.get(bucket) or []:
                    if isinstance(row, dict):
                        keys.add(f"{row.get('repo')}|{row.get('task')}|{row.get('id')}")
            out[str(q)] = keys
        f = Path(h) / "focus.json"
        try:
            fd = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
        except Exception:
            fd = None
        if isinstance(fd, dict):
            out[str(f)] = set((fd.get("repos") or {}).keys()) | set((fd.get("items") or {}).keys())
    return out


def live_state_damage(before: dict, after: dict, *, max_lost: int = 15) -> list[str]:
    """Flag real wipe / mass loss only.

    Queue and focus use the same ``max_lost`` threshold (#4185 / #4408 / FR #5042).
    A concurrent chair resync may prune closed focus items (FR #1508 / #1520) or purge
    many closed/done queue rows while a long suite step runs; that is not suite damage.
    Default ``max_lost`` is 15 so a busy chair (queue.json lost ~10 during jeeves@HEAD)
    does not abort !build. Mass wipe still fails closed: empty after a non-empty before,
    or more than half the keys gone when the prior set was sizeable (#4183 wipe case).
    """
    bad = []
    for k, was in before.items():
        now = after.get(k, set())
        if not isinstance(was, set):
            was = set(was or ())
        if not isinstance(now, set):
            now = set(now or ())
        lost = was - now
        n_lost = len(lost)
        if n_lost == 0:
            continue
        n_was = len(was)
        # Soft concurrent-prune ceiling; caller may pass a tighter max_lost in tests.
        soft = max(int(max_lost), 0)
        mass_wipe = (n_was > 0 and len(now) == 0) or (
            n_was >= 8 and n_lost > (n_was // 2)
        )
        if mass_wipe or n_lost > soft:
            bad.append(f"{k} lost {n_lost}")
    return bad


class LiveStateTouched(RuntimeError):
    pass


# #4188: steps that call ``gh`` against GitHub (post-release asset assert). Suites stay
# token-less (#4183); only these named steps get the runner's GH_TOKEN back.
GH_AUTH_STEPS = frozenset({"assert"})

# FR #4349: airc pack (FR #4216) must embed Ergo PASS. Isolation blanks AGENTIC/BOB_IRC and
# remaps USERPROFILE, so inject AIRC_PACK_ERGO_PASSWORD for pack only (never for suites).
PACK_SECRET_STEPS = frozenset({"pack"})


def gh_auth_env(source_env: dict | None = None) -> dict:
    """GH_TOKEN for a gh step, taken from the runner env (never logged). Empty dict if none."""
    src = os.environ if source_env is None else source_env
    tok = (src.get("GH_TOKEN") or src.get("GITHUB_TOKEN") or "").strip()
    return {"GH_TOKEN": tok, "GITHUB_TOKEN": tok} if tok else {}


def pack_ergo_env(source_env: dict | None = None) -> dict:
    """AIRC_PACK_ERGO_PASSWORD for the pack step from the live runner (never logged).

    Reads real runner env / fleet install paths — not the isolated suite USERPROFILE (#4349).
    """
    src = os.environ if source_env is None else source_env
    for key in (
        "AIRC_PACK_ERGO_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
    ):
        val = (src.get(key) or "").strip()
        if val:
            return {"AIRC_PACK_ERGO_PASSWORD": val}
    cands: list[Path] = []
    up = (src.get("USERPROFILE") or src.get("HOME") or "").strip()
    if up:
        cands.append(Path(up) / ".grok" / "ergo" / "connect.password")
        cands.append(Path(up) / ".grok" / "ergo" / "ergo.password")
    ai_roots: list[str] = []
    bob_ai = (src.get("BOB_AI_ROOT") or os.environ.get("BOB_AI_ROOT") or "").strip()
    if bob_ai:
        ai_roots.append(bob_ai)
    for root in (r"C:\ai", r"D:\ai"):
        if root not in ai_roots:
            ai_roots.append(root)
    for root in ai_roots:
        for prod in ("bob", "airc", "jeeves"):
            cands.append(Path(root) / prod / "config" / "ergo.password")
    for path in cands:
        try:
            if path.is_file():
                body = path.read_text(encoding="utf-8").strip()
                if body:
                    return {"AIRC_PACK_ERGO_PASSWORD": body}
        except OSError:
            continue
    return {}


GH_AUTH_MISSING = (
    "gh auth missing: the build runner has no GitHub token for gh (needed for release + "
    "Assert-BobiverseReleaseAssets). Put a token in <install>\\config\\github.token "
    "(or set GH_TOKEN for the service) and rerun (#4188)."
)


def gh_auth_preflight(gh_runner: Callable | None = None, env: dict | None = None) -> str | None:
    """None when ``gh`` is authenticated for this process, else a clear refusal line (#4188)."""
    import subprocess as _sp

    runner = gh_runner or _sp.run
    src = dict(os.environ if env is None else env)
    try:
        cp = runner(["gh", "auth", "status", "--hostname", "github.com"],
                    capture_output=True, text=True, check=False, env=src)
    except (OSError, FileNotFoundError) as exc:
        return f"{GH_AUTH_MISSING} ({type(exc).__name__})"
    if int(getattr(cp, "returncode", 1) or 0) != 0:
        return GH_AUTH_MISSING
    return None


def guarded_run_command(work_dir: Path | str, live_homes: Iterable[Path | str], inner: Callable | None = None,
                        gh_steps: Iterable[str] = GH_AUTH_STEPS,
                        pack_secret_steps: Iterable[str] = PACK_SECRET_STEPS) -> Callable:
    """run_command_fn: isolated env for every step + fail closed if live chair state changes.

    Steps named in ``gh_steps`` get GH_TOKEN from the runner env (#4188); others stay blanked.
    Isolation home/URL keys always win over ``suite.env`` (FR #4315).
    Pack steps then get AIRC_PACK_ERGO_PASSWORD from the live runner (FR #4349 / #4216).
    """
    inner = inner or run_command
    homes = [Path(h) for h in live_homes]
    gh_steps = frozenset(gh_steps)
    pack_secret_steps = frozenset(pack_secret_steps)

    def _run(
        cmd,
        cwd=None,
        env=None,
        timeout=None,
        *,
        name="cmd",
        ref_or_baseline="",
        log_path=None,
    ):
        iso = isolated_suite_env(work_dir, f"{name}-{ref_or_baseline}")
        merged = dict(env or {})
        # Isolation wins over suite.env for homes/URLs (FR #4315); blanks GH/IRC secrets.
        merged.update(iso)
        # Re-inject after iso: assert needs GH (#4188); pack needs Ergo PASS for airc (#4349/#4216).
        if name in gh_steps:
            merged.update(gh_auth_env())
        if name in pack_secret_steps:
            merged.update(pack_ergo_env())
        before = live_state_fingerprint(homes)
        res = inner(
            cmd,
            cwd=cwd,
            env=merged,
            timeout=timeout,
            name=name,
            ref_or_baseline=ref_or_baseline,
            log_path=log_path,
        )
        after = live_state_fingerprint(homes)
        damage = live_state_damage(before, after)
        if damage:
            try:
                logs = Path(work_dir) / "logs"
                logs.mkdir(parents=True, exist_ok=True)
                (logs / f"{name}-{re.sub(r'[^A-Za-z0-9_.-]+', '_', str(ref_or_baseline))}-guard.log").write_text(
                    str(getattr(res, "stdout", "") or ""), encoding="utf-8"
                )
            except Exception:
                pass
            raise LiveStateTouched(f"step {name}@{ref_or_baseline} damaged live state: {', '.join(damage)}")
        return res

    return _run
