"""Repo-generic BUILD job (FR #4006 / #4025) + INSTALL-TEST (FR #4026 WP3).

WP1: load/validate .bobiverse/build.yml, classify failures, single-flight lock,
ops `!build` parse/decide, dry-run plans (no agent tokens).

WP2 (FR #4025): deterministic live runner (`BuildRunner`), FakeGitHubFiler,
`BUILD v1` consume/enqueue, pack/release only when no new blockers.

WP3 (FR #4026): optional `!installtest` --- msiexec pre-release MSIs + post-checks + blockers.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import zipfile
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


def append_pytest_nodeid(cmd: str, nodeid: str) -> str:
    """Append a single nodeid for per-test solo rerun (FR #5121)."""
    c = (cmd or "").rstrip()
    n = (nodeid or "").strip()
    if not n:
        return c
    return f"{c} {n}"


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
    refusal = version_refusal(version)
    if refusal:
        return BuildDecision(False, "bad_version", [refusal], dry_run=dry)
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
    r"^BUILD\s+v1\s+repos=(?P<repos>\S+)\s+version=(?P<version>\S+)\s+ref=(?P<ref>\S+)"
    r"(?:\s+id=(?P<id>\S+))?\s*$",
    re.IGNORECASE,
)

INSTALLTEST_V1_RE = re.compile(
    r"^INSTALLTEST\s+v1\s+repo=(?P<repo>\S+)\s+version=(?P<version>\S+)\s+tag=(?P<tag>\S+)\s*$",
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
        "id": (m.group("id") or "").strip(),
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
        baseline_root: Path | str | None = None,
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
            try:
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
                    cwd=self._suite_cwd(suite, baseline=True),
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
                        for tid in new_ids:
                            solo_cmd = append_pytest_nodeid(rendered_cmd, tid)
                            solo = self.run_command_fn(
                                solo_cmd,
                                cwd=self._suite_cwd(suite),
                                env=dict(suite.env or {}),
                                timeout=float(suite.timeout),
                                name=suite.name,
                                ref_or_baseline=f"{self.ref}-solo",
                            )
                            report.suite_results.append(solo)
                            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tid)[:80]
                            self._write_log(f"{suite.name}-solo-{safe}.log", solo.stdout)
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
            urls = [
                str(b.get("url") or "").strip()
                for b in report.blockers_filed
                if str(b.get("url") or "").strip()
            ]
            url_bit = (" blocker=" + " ".join(urls)) if urls else ""
            report.announce_lines.append(
                f"BUILD fail {self.repo} version={self.version} ref={self.ref} "
                f"blockers={n} pack={report.pack_ok} release={report.release_ok}{url_bit}"
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


def claim_build_route_marker(marker_dir: Path | str, route_id: str) -> bool:
    """O_EXCL claim. First caller True; later callers on the same id False."""
    rid = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in str(route_id or "").strip())
    if not rid:
        rid = "unknown"
    d = Path(marker_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rid}.claimed"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError:
        return False
    except OSError:
        return False
    try:
        os.write(fd, f"{int(time.time())}\n".encode("ascii"))
    finally:
        os.close(fd)
    return True


def consume_build_v1(
    line: str,
    local_machine: str,
    recipe_machine: str,
    *,
    queue_dir: Path | str | None = None,
    route_marker_dir: Path | str | None = None,
) -> bool:
    """Return True when this host should accept the BUILD v1 route (optionally enqueue).

    Does not pack/release in-process; writes a job JSON when ``queue_dir`` is set.
    FR #5266: when ``route_marker_dir`` is set, the first caller on this machine
    claims the route id with O_EXCL; later chair/ear copies return False.
    """
    route = parse_build_v1_route(line)
    if not route:
        return False
    if not is_recipe_build_machine(recipe_machine, local_machine):
        return False
    if route_marker_dir is not None:
        if not claim_build_route_marker(route_marker_dir, build_route_id(route)):
            return False
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


def fetch_remote_recipe(repo: str, *, gh_runner: Callable | None = None) -> BuildRecipe | None:
    """Load ``.bobiverse/build.yml`` from GitHub for ``repo``; None when the repo has none."""
    import subprocess as _sp
    import tempfile as _tf

    runner = gh_runner or _sp.run
    cp = runner(
        [
            "gh", "api", f"repos/{normalize_repo(repo)}/contents/.bobiverse/build.yml",
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

    def _run(cmd, cwd=None, env=None, timeout=None, *, name="cmd", ref_or_baseline=""):
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
        res = inner(cmd, cwd=cwd, env=merged, timeout=timeout, name=name, ref_or_baseline=ref_or_baseline)
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
