"""Repo-generic BUILD job (FR #4006 / #4025) --- recipe, classify, lock, dry-run, live runner.

WP1: load/validate .bobiverse/build.yml, classify failures, single-flight lock,
ops `!build` parse/decide, dry-run plans (no agent tokens).

WP2 (FR #4025): deterministic live runner (`BuildRunner`), FakeGitHubFiler,
`BUILD v1` consume/enqueue, pack/release only when no new blockers.
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

# ------------------------------------------------------------------ WP2 runner (FR #4025)


BUILD_V1_RE = re.compile(
    r"^BUILD\s+v1\s+repos=(?P<repos>\S+)\s+version=(?P<version>\S+)\s+ref=(?P<ref>\S+)\s*$",
    re.IGNORECASE,
)

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
        "raw": raw,
    }


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
            "repo": repo,
            "kind": failure.kind,
        }
    title = f"release-blocker: {failure.test_id} ({version})"
    created = filer.create_issue(repo, title, body, labels=labels)
    return {
        "action": "created",
        "number": int(created["number"]),
        "repo": repo,
        "kind": failure.kind,
        "labels": labels,
    }


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


def run_command(
    cmd: str | list,
    cwd: str | Path | None = None,
    env: dict | None = None,
    timeout: float | None = None,
    runner: Any = None,
    *,
    name: str = "cmd",
    ref_or_baseline: str = "",
) -> SuiteRunResult:
    """Run a shell command with hard timeout (FR #3965 class). Injectable ``runner``.

    On timeout the process is killed and ``timed_out=True`` (exit_code=-1).
    """
    import subprocess as _sp

    sp = runner if runner is not None else _sp
    cwd_s = str(cwd) if cwd is not None else None
    env_map = None
    if env:
        import os as _os

        env_map = dict(_os.environ)
        env_map.update({str(k): str(v) for k, v in env.items()})
    t0 = time.time()
    timed_out = False
    exit_code = -1
    stdout = ""
    try:
        popen_kw = dict(
            cwd=cwd_s,
            env=env_map,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            universal_newlines=True,
        )
        if isinstance(cmd, (list, tuple)):
            proc = sp.Popen(list(cmd), **popen_kw)
        else:
            proc = sp.Popen(str(cmd), shell=True, **popen_kw)
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
    except Exception as exc:
        stdout = f"{type(exc).__name__}: {exc}"
        exit_code = -1
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
    ) -> None:
        self.repo_root = Path(repo_root)
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

    def _zip_logs(self) -> Path:
        import zipfile

        zip_path = self.work_dir / f"build-logs-{self.version}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if self.log_dir.is_dir():
                for f in sorted(self.log_dir.rglob("*")):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(self.log_dir)))
        return zip_path

    def _suite_cwd(self, suite: SuiteSpec) -> str:
        if suite.cwd in (".", "", None):
            return str(self.repo_root)
        return str(self.repo_root / suite.cwd)

    def run(self, *, dry_run: bool = False) -> BuildReport:
        report = BuildReport(ok=False)
        if not is_recipe_build_machine(self.recipe.machine, self.local_machine):
            report.errors.append(
                f"not recipe machine recipe={self.recipe.machine} local={self.local_machine}"
            )
            report.announce_lines.append(
                f"BUILD fail {self.repo} version={self.version}: wrong machine"
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

        for suite in self.recipe.suites:
            rendered_cmd = render_template(
                suite.cmd,
                version=self.version,
                out_dir=str(out_dir),
                ref=self.ref,
            )
            ref_res = self.run_command_fn(
                rendered_cmd,
                cwd=self._suite_cwd(suite),
                env=dict(suite.env or {}),
                timeout=float(suite.timeout),
                name=suite.name,
                ref_or_baseline=self.ref,
            )
            report.suite_results.append(ref_res)
            self._write_log(f"{suite.name}-ref.log", ref_res.stdout)
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

            ref_failed = int(ref_res.exit_code) != 0

            base_cmd = render_template(
                suite.cmd,
                version=self.version,
                out_dir=str(out_dir),
                ref=baseline,
            )
            base_res = self.run_command_fn(
                base_cmd,
                cwd=self._suite_cwd(suite),
                env=dict(suite.env or {}),
                timeout=float(suite.timeout),
                name=suite.name,
                ref_or_baseline=baseline,
            )
            report.suite_results.append(base_res)
            self._write_log(f"{suite.name}-baseline.log", base_res.stdout)
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

            solo_passed = False
            if ref_failed and not ref_res.timed_out:
                solo = self.run_command_fn(
                    rendered_cmd,
                    cwd=self._suite_cwd(suite),
                    env=dict(suite.env or {}),
                    timeout=float(suite.timeout),
                    name=suite.name,
                    ref_or_baseline=f"{self.ref}-solo",
                )
                report.suite_results.append(solo)
                self._write_log(f"{suite.name}-solo.log", solo.stdout)
                if solo.timed_out:
                    failure = classify_step_failure(f"suite:{suite.name}:solo-timeout")
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

            if ref_failed:
                failure = classify_failure(
                    suite.name,
                    ref_failed=True,
                    baseline_failed=baseline_failed,
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

        if blocking:
            report.errors.append("blockers present; skipping pack/release")
            report.pack_ok = False
            report.release_ok = False
        else:
            try:
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
                if report.pack_ok and assert_cmd and self.pack_fn is None:
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
                report.errors.append(f"pack: {type(exc).__name__}: {exc}")
                report.pack_ok = False
                blocking = True
                assets = []

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
                    if self.release_fn is not None:
                        self.release_fn(
                            tag=tag,
                            assets=assets,
                            prerelease=True,
                            latest=(False if never_latest else None),
                        )
                        report.release_ok = True
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
            )
        else:
            n = len(report.blockers_filed)
            report.announce_lines.append(
                f"BUILD fail {self.repo} version={self.version} ref={self.ref} "
                f"blockers={n} pack={report.pack_ok} release={report.release_ok}"
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
        "local_machine": local_machine,
        "recipe_machine": recipe_machine,
        "queued_at": ts,
        "status": "queued",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def consume_build_v1(
    line: str,
    local_machine: str,
    recipe_machine: str,
    *,
    queue_dir: Path | str | None = None,
) -> bool:
    """Return True when this host should accept the BUILD v1 route (optionally enqueue).

    Does not pack/release in-process; writes a job JSON when ``queue_dir`` is set.
    """
    route = parse_build_v1_route(line)
    if not route:
        return False
    if not is_recipe_build_machine(recipe_machine, local_machine):
        return False
    if queue_dir is not None:
        enqueue_build_job(
            route,
            queue_dir=queue_dir,
            local_machine=local_machine,
            recipe_machine=recipe_machine,
        )
    return True
