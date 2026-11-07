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
) -> dict[str, Any]:
    """Scoped file discovery without Unix grep/head.

    Walks ``root`` with pathlib, matches ``needle`` (case-insensitive) in
    file names or UTF-8 text for the given extensions. Bounded by ``max_hits``.
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
            if not path.is_file():
                continue
            if path.suffix.lower() not in exts:
                continue
            scanned += 1
            name_hit = needle_l in path.name.lower()
            body_hit = False
            if not name_hit:
                try:
                    raw = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                body_hit = needle_l in raw.lower()
            if name_hit or body_hit:
                hits.append(str(path))
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


def classify_gh_auth(
    *,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any]:
    """Classify ``gh auth status`` without reading hosts.yml or token files.

    Missing auth → blocked with supported next step (gh auth login). Never
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
    if code == 0 and ("logged in" in low or "✓" in out or "active account" in low):
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
) -> dict[str, Any]:
    """Combine classifiers into one readiness verdict (no false DONE)."""
    blockers = []
    next_steps = []
    for part in (search, worktree, gh):
        if not part.get("ok"):
            b = part.get("blocker") or part.get("error") or part.get("state") or "blocked"
            blockers.append(str(b))
            ns = part.get("next_step") or ""
            if ns:
                next_steps.append(str(ns))
    ok = bool(search.get("ok") and worktree.get("ok") and gh.get("ok"))
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
