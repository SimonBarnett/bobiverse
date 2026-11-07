"""FR #6240: OpenCode Windows worker readiness classifiers (no secrets).

Pure helpers for native file search, consented worktree access, and gh auth
preflight. Never searches credential stores or reads hosts.yml / token files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Extensions used by the FR-6240 scoped discovery contract.
DEFAULT_EXTS = (".py", ".cs", ".ps1", ".md")
# Cap content reads so a huge file cannot stall readiness (name hits still count).
MAX_READ_BYTES = 1 * 1024 * 1024

_SECRETISH = re.compile(
    r"(?i)(github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|gho_[A-Za-z0-9]+|"
    r"ghu_[A-Za-z0-9]+|ghs_[A-Za-z0-9]+|ghr_[A-Za-z0-9]+|"
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*)"
)


def redact_secrets(text: str) -> str:
    """Strip token-shaped substrings from status/error text."""
    if not text:
        return ""
    return _SECRETISH.sub("[REDACTED]", text)


def windows_native_search(
    root: str | Path,
    *,
    needle: str = "opencode",
    extensions: tuple[str, ...] = DEFAULT_EXTS,
    max_hits: int = 50,
    max_read_bytes: int = MAX_READ_BYTES,
) -> dict[str, Any]:
    """Scoped file discovery without Unix grep/head.

    Walks ``root`` with pathlib, matches ``needle`` (case-insensitive) in
    file names or UTF-8 text for the given extensions. Bounded by ``max_hits``.
    Per-entry OSError is skipped; content reads above ``max_read_bytes`` are
    skipped (filename matches still count).
    """
    base = Path(root)
    hits: list[str] = []
    scanned = 0
    if not base.is_dir():
        return {
            "ok": False,
            "hits": [],
            "scanned": 0,
            "error": "root_missing",
            "tool": "pathlib",
        }
    needle_l = (needle or "").lower()
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    try:
        for path in base.rglob("*"):
            if len(hits) >= max(1, int(max_hits)):
                break
            try:
                if not path.is_file():
                    continue
                if path.suffix.lower() not in exts:
                    continue
                scanned += 1
                name_hit = needle_l in path.name.lower()
                body_hit = False
                if not name_hit:
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    if size > max(1, int(max_read_bytes)):
                        continue
                    try:
                        raw = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    body_hit = needle_l in raw.lower()
                if name_hit or body_hit:
                    hits.append(str(path))
            except OSError:
                continue
    except OSError as exc:
        return {
            "ok": False,
            "hits": hits,
            "scanned": scanned,
            "error": redact_secrets(str(exc)),
            "tool": "pathlib",
        }
    return {
        "ok": True,
        "hits": hits,
        "scanned": scanned,
        "error": "",
        "tool": "pathlib",
        "needle": needle,
        "max_hits": int(max_hits),
    }


def classify_worktree_access(
    *,
    cwd: str | Path | None,
    worktree: str | Path | None,
    permission: str = "authorized",
) -> dict[str, Any]:
    """Classify job-worktree access under OpenCode external_directory consent.

    ``permission`` is the supported approval-flow outcome:
      authorized | missing | rejected

    Denial stays effective: rejected never becomes ok. Missing permission never
    invents access. When authorized, cwd must resolve to the worktree (or be
    inside it) so the seat is not reaching an external path from install CWD.
    """
    perm = (permission or "").strip().lower()
    wt = Path(worktree).resolve() if worktree else None
    cur = Path(cwd).resolve() if cwd else None

    if perm == "rejected":
        return {
            "ok": False,
            "state": "rejected",
            "blocker": "worktree_permission_rejected",
            "next_step": (
                "Request narrowly scoped external_directory consent for the "
                "assigned worktree via the supported approval flow, or relaunch "
                "with CWD set to that worktree. Do not bypass the denial."
            ),
        }
    if perm == "missing":
        return {
            "ok": False,
            "state": "missing_permission",
            "blocker": "worktree_permission_missing",
            "next_step": (
                "Obtain legitimate consent for the assigned worktree before "
                "git status/log/diff, or start the seat with CWD=worktree."
            ),
        }
    if perm != "authorized":
        return {
            "ok": False,
            "state": "unknown_permission",
            "blocker": "worktree_permission_unknown",
            "next_step": "Pass permission=authorized|missing|rejected from the approval flow.",
        }
    if wt is None:
        return {
            "ok": False,
            "state": "no_worktree",
            "blocker": "worktree_path_missing",
            "next_step": "Pass the assigned Get-BobiverseJobWorktreePath result.",
        }
    if not wt.is_dir():
        return {
            "ok": False,
            "state": "worktree_missing_on_disk",
            "blocker": "worktree_not_found",
            "next_step": "Create the job worktree (git worktree add) then re-run readiness.",
        }
    if cur is None:
        return {
            "ok": False,
            "state": "cwd_missing",
            "blocker": "cwd_unset",
            "next_step": "Set process CWD to the assigned worktree before tool use.",
        }
    try:
        cur.relative_to(wt)
        inside = True
    except ValueError:
        inside = cur == wt
    if not inside:
        return {
            "ok": False,
            "state": "cwd_outside_worktree",
            "blocker": "external_directory_risk",
            "next_step": (
                "Relaunch OpenCode with CWD at the assigned worktree, or request "
                "narrow external_directory consent. Do not search credential stores."
            ),
            "cwd": str(cur),
            "worktree": str(wt),
        }
    return {
        "ok": True,
        "state": "authorized",
        "blocker": "",
        "next_step": "",
        "cwd": str(cur),
        "worktree": str(wt),
    }


def classify_git_worktree(
    *,
    status_exit: int | None,
    status_stdout: str = "",
    status_stderr: str = "",
    branch_exit: int | None = None,
    branch_stdout: str = "",
    branch_stderr: str = "",
) -> dict[str, Any]:
    """Classify read-only ``git status`` / ``git branch`` against the worktree.

    Does not mutate the tree. Non-zero status/branch exits block readiness.
    """
    s_code = 0 if status_exit is None else int(status_exit)
    b_code = 0 if branch_exit is None else int(branch_exit)
    s_out = redact_secrets((status_stdout or "") + "\n" + (status_stderr or ""))
    b_out = redact_secrets((branch_stdout or "") + "\n" + (branch_stderr or ""))
    if s_code != 0:
        return {
            "ok": False,
            "state": "status_failed",
            "blocker": "git_status_failed",
            "next_step": (
                "Run `git -C <worktree> status` after consent/CWD=worktree. "
                "Fix the git error; do not search credential stores."
            ),
            "detail": redact_secrets(s_out.strip()[:240]),
        }
    if b_code != 0:
        return {
            "ok": False,
            "state": "branch_failed",
            "blocker": "git_branch_failed",
            "next_step": (
                "Run `git -C <worktree> branch --show-current` (or `git branch`) "
                "after consent. Fix the git error; do not widen external_directory."
            ),
            "detail": redact_secrets(b_out.strip()[:240]),
        }
    branch = (branch_stdout or "").strip().splitlines()[0].strip() if (branch_stdout or "").strip() else ""
    return {
        "ok": True,
        "state": "git_ok",
        "blocker": "",
        "next_step": "",
        "branch": branch,
        "detail": "git status/branch ok (output redacted)",
    }


def classify_gh_auth(
    *,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any]:
    """Classify ``gh auth status`` without reading hosts.yml or token files.

    Missing auth -> blocked with supported next step (gh auth login). Never
    suggests credential-store discovery.
    """
    out = redact_secrets((stdout or "") + "\n" + (stderr or ""))
    low = out.lower()
    code = 0 if exit_code is None else int(exit_code)

    if "gh auth login" in low or "to get started with github cli" in low:
        return {
            "ok": False,
            "state": "missing",
            "blocker": "gh_auth_missing",
            "next_step": (
                "Run supported `gh auth login` (or user-approved provisioning) "
                "in the worker context. Do not search profiles for tokens, "
                "do not read hosts.yml, do not invent GH_TOKEN."
            ),
            "detail": redact_secrets(out.strip()[:240]),
        }
    if code != 0 and ("not logged" in low or "logged out" in low or "no oauth" in low):
        return {
            "ok": False,
            "state": "missing",
            "blocker": "gh_auth_missing",
            "next_step": (
                "Run supported `gh auth login` in the worker context. "
                "Do not hunt credentials as a fallback."
            ),
            "detail": redact_secrets(out.strip()[:240]),
        }
    if code == 0 and ("logged in" in low or "\u2713" in out or "active account" in low):
        return {
            "ok": True,
            "state": "authorized",
            "blocker": "",
            "next_step": "",
            "detail": "gh auth status: logged in (token redacted)",
        }
    if code != 0:
        return {
            "ok": False,
            "state": "error",
            "blocker": "gh_auth_error",
            "next_step": "Re-run `gh auth status`; if still failing use `gh auth login`. Never read credential files.",
            "detail": redact_secrets(out.strip()[:240]),
        }
    return {
        "ok": False,
        "state": "unknown",
        "blocker": "gh_auth_unknown",
        "next_step": "Re-run `gh auth status` and escalate if unclear. Never open hosts.yml.",
        "detail": redact_secrets(out.strip()[:240]),
    }


def classify_pr_lookup(
    *,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
    expected_repo: str = "SimonBarnett/bobiverse",
    expected_number: int = 6147,
) -> dict[str, Any]:
    """Classify a scoped read-only ``gh pr view`` / ``gh pr list`` result.

    Used after ``gh auth status`` is authorized. Never invents GH_TOKEN.
    """
    code = 0 if exit_code is None else int(exit_code)
    out = redact_secrets((stdout or "") + "\n" + (stderr or ""))
    low = out.lower()
    if "gh auth login" in low or "to get started with github cli" in low:
        return {
            "ok": False,
            "state": "missing_auth",
            "blocker": "gh_auth_missing",
            "next_step": (
                "Run supported `gh auth login` before PR lookup. "
                "Do not read hosts.yml or invent GH_TOKEN."
            ),
            "detail": redact_secrets(out.strip()[:240]),
        }
    if code != 0:
        return {
            "ok": False,
            "state": "lookup_failed",
            "blocker": "pr_lookup_failed",
            "next_step": (
                f"Re-run `gh pr view {int(expected_number)} --repo {expected_repo}` "
                "after auth is healthy. Escalate if still failing; never hunt tokens."
            ),
            "detail": redact_secrets(out.strip()[:240]),
        }
    # Accept JSON number field or plain URL/title mentioning the PR number.
    num = str(int(expected_number))
    repo_l = (expected_repo or "").lower()
    if num in out.replace(" ", "") or f"pull/{num}" in low or f"#{num}" in out:
        if repo_l and repo_l not in low and "github.com/" + repo_l.lower() not in low:
            # JSON-only bodies may omit the owner/repo string; number match is enough
            # when exit 0 from an explicit --repo invocation.
            pass
        return {
            "ok": True,
            "state": "found",
            "blocker": "",
            "next_step": "",
            "detail": f"scoped PR lookup ok for {expected_repo}#{num} (redacted)",
            "repo": expected_repo,
            "number": int(expected_number),
        }
    return {
        "ok": False,
        "state": "not_found",
        "blocker": "pr_lookup_mismatch",
        "next_step": (
            f"Confirm `gh pr view {num} --repo {expected_repo}` returns that PR. "
            "Do not claim readiness without a matching scoped lookup."
        ),
        "detail": redact_secrets(out.strip()[:240]),
    }


def forbidden_credential_probe_paths() -> tuple[str, ...]:
    """Paths readiness must never search/read when gh auth is missing."""
    return (
        r"%USERPROFILE%\.config\gh\hosts.yml",
        r"%USERPROFILE%\.config\gh",
        r"%USERPROFILE%\.git-credentials",
        r"%USERPROFILE%\.netrc",
        r"D:\ai\agentic_irc",
    )


def summarize_readiness(
    *,
    search: dict[str, Any],
    worktree: dict[str, Any],
    gh: dict[str, Any],
    git: dict[str, Any] | None = None,
    pr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine classifiers into one readiness verdict (no false DONE)."""
    blockers = []
    next_steps = []
    parts = [search, worktree, gh]
    if git is not None:
        parts.append(git)
    if pr is not None:
        parts.append(pr)
    for part in parts:
        if not part.get("ok"):
            b = part.get("blocker") or part.get("error") or part.get("state") or "blocked"
            blockers.append(str(b))
            ns = part.get("next_step") or ""
            if ns:
                next_steps.append(str(ns))
    ok = all(bool(p.get("ok")) for p in parts)
    return {
        "ok": ok,
        "blockers": blockers,
        "next_steps": next_steps,
        "completed": False if not ok else True,
        "message": (
            "ready"
            if ok
            else "blocked: " + "; ".join(blockers)
        ),
    }