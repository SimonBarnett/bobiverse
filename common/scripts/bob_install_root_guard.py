"""FR #4843: refuse job git that targets the live bob install root.

Seats must use a linked job worktree (``git worktree add``) for FR/FIX/MRB
checkout/commit. Switching the install root itself onto ``fr-*`` leaves the
live tray/ear/skills on an unreviewed branch.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

# Ops that must never run against the install-root checkout itself.
JOB_GIT_OPS = frozenset(
    {
        "checkout",
        "switch",
        "commit",
        "merge",
        "rebase",
        "cherry-pick",
        "reset",
        "branch",
        "am",
        "revert",
    }
)

RunFn = Callable[..., subprocess.CompletedProcess]


def _norm(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def paths_equal(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(str(_norm(a))) == os.path.normcase(str(_norm(b)))


def git_toplevel(path: str | Path, *, run: RunFn = subprocess.run) -> Optional[Path]:
    """Return the git toplevel for *path*, or None if not inside a work tree."""
    p = _norm(path)
    try:
        r = run(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    top = (r.stdout or "").strip()
    if not top:
        return None
    return _norm(top)


def is_install_root_git_target(target: str | Path, install_root: str | Path, *, run: RunFn = subprocess.run) -> bool:
    """True when *target* is the install root checkout (or resolves to its toplevel)."""
    root = _norm(install_root)
    t = _norm(target)
    if paths_equal(t, root):
        return True
    top = git_toplevel(t, run=run)
    if top is not None and paths_equal(top, root):
        return True
    # Path under install root whose git toplevel is that install (sparse work tree).
    try:
        t.relative_to(root)
    except ValueError:
        return False
    return top is not None and paths_equal(top, root)


def suggest_job_worktree(install_root: str | Path, *, mode: str = "fr", issue_n: str | int = "N") -> str:
    """Canonical sibling job-worktree path suggestion (MarchHare ``bob-wt-fr-<n>`` style)."""
    root = _norm(install_root)
    mode_l = str(mode or "fr").strip().lower() or "fr"
    return str(root.parent / f"bob-wt-{mode_l}-{issue_n}")


def refuse_job_git(
    *,
    op: str,
    target: str | Path,
    install_root: str | Path,
    issue_n: str | int = "N",
    mode: str = "fr",
    run: RunFn = subprocess.run,
) -> Optional[str]:
    """Return a refusal message when *op* against *target* hits the install root; else None.

    Callers (agent playbooks, helpers, future hooks) must treat a non-None return as
    hard refuse: do not run the git command; create a job worktree instead.
    """
    op_l = str(op or "").strip().lower()
    # Accept ``checkout -b`` style: first token is the verb.
    if op_l not in JOB_GIT_OPS:
        first = op_l.split(None, 1)[0] if op_l else ""
        if first not in JOB_GIT_OPS:
            return None
        op_l = first
    if not is_install_root_git_target(target, install_root, run=run):
        return None
    tip = suggest_job_worktree(install_root, mode=mode, issue_n=issue_n)
    root = _norm(install_root)
    return (
        f"FR #4843: refuse git {op_l} in install root {root}. "
        f"Use a job worktree, e.g. "
        f"git -C \"{root}\" worktree add -b {mode}-{issue_n} \"{tip}\" origin/main"
    )


def read_install_branch(install_root: str | Path, *, run: RunFn = subprocess.run) -> Optional[str]:
    """Return the install-root HEAD branch name, or None when unknown / not a repo."""
    root = _norm(install_root)
    try:
        r = run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    name = (r.stdout or "").strip()
    return name or None


def install_root_branch_warning(
    install_root: str | Path,
    *,
    expected: str = "main",
    run: RunFn = subprocess.run,
) -> Optional[str]:
    """Warn when the live install checkout is not on *expected* (default ``main``).

    Detached HEAD (``HEAD``) is also warned --- seats must not leave the install
    off the fast-forward service branch.
    """
    branch = read_install_branch(install_root, run=run)
    if branch is None:
        return None
    if branch == expected:
        return None
    root = _norm(install_root)
    return (
        f"install-root: WARN FR #4843 branch={branch} expected={expected} "
        f"path={root} (do not run FR/FIX/MRB git in the install root; "
        f"use git worktree add -> bob-wt-<mode>-<n>)"
    )
