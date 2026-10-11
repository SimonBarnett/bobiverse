"""Repo-generic BUILD job (FR #4006) — recipe, classify, lock, dry-run (no agent tokens).

Live suite/pack/release execution on the build machine is WP2; this module owns the
deterministic contract: load/validate `.bobiverse/build.yml`, classify failures,
single-flight lock, ops ``!build`` parse/decide, and dry-run plans.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML may be absent in slim envs
    yaml = None  # type: ignore

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RELEASE_BLOCKER_LABEL = "release-blocker"
FEATURE_REQUEST_LABEL = "feature-request"


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
    if sub in ("status", "cancel", "dry-run", "dryrun", "dry"):
        return True, "dry-run" if sub in ("dry-run", "dryrun", "dry") else sub, rest
    # !build <repos> <version> [ref]
    return True, "run", text[len("!build") :].strip()


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
                "build: also !build status|cancel|dry-run ...",
            ],
            dry_run=dry,
        )
    try:
        repos = parse_repos_csv(tokens[0])
    except ValueError as exc:
        return BuildDecision(False, "bad_repo", [f"build: {exc}"], dry_run=dry)
    version = tokens[1]
    ref = tokens[2] if len(tokens) > 2 else "HEAD"
    if not repos:
        return BuildDecision(False, "usage", ["build: need at least one owner/repo"], dry_run=dry)

    lines: list[str] = []
    ok_repos: list[str] = []
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
        bid = (new_build_id or (lambda: f"b-{int(time.time())}"))()
        if not dry and lock is not None:
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
        route = f"BUILD v1 repos={','.join(ok_repos)} version={version} ref={ref}"
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
