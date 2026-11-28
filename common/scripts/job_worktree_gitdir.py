"""FR #10245: detect a job worktree whose git metadata is broken.

A linked job worktree has a ``.git`` gitfile (``gitdir: <path>``) pointing at
``<common>/.git/worktrees/<name>/``. That metadata dir must hold ``HEAD``,
``gitdir`` and ``commondir``. When any of them is missing (or the gitfile
target does not exist) every ``git`` command fails with "gitfile does not point
to a valid repository", so claimed in-worktree work cannot be committed or
pushed. Seats call this before ACK/work and NACK/GIVEUP with the reason
instead of claiming work they cannot land.

Usage: ``python common/scripts/job_worktree_gitdir.py <worktree>``
Exit 0 when healthy, 1 with the reason on stdout when broken.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

REQUIRED_METADATA = ("HEAD", "gitdir", "commondir")


def linked_worktree_problem(worktree: str | Path) -> Optional[str]:
    """Return a human reason when *worktree* has broken linked-worktree git metadata, else None."""
    root = Path(worktree)
    git = root / ".git"
    if git.is_dir():
        return None  # full clone / install root: nothing linked to validate
    if not git.is_file():
        return f"no .git in {root}"
    try:
        raw = git.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return f"cannot read .git gitfile: {exc}"
    if not raw.lower().startswith("gitdir:"):
        return ".git is a file but not a gitdir pointer"
    meta = Path(raw.split(":", 1)[1].strip())
    if not meta.is_absolute():
        meta = (root / meta).resolve()
    if not meta.is_dir():
        return f"gitfile target missing: {meta}"
    missing = [name for name in REQUIRED_METADATA if not (meta / name).is_file()]
    if missing:
        return f"worktree metadata incomplete in {meta}: missing {', '.join(missing)}"
    common = (meta / "commondir").read_text(encoding="utf-8", errors="replace").strip()
    common_dir = Path(common) if Path(common).is_absolute() else (meta / common).resolve()
    if not common_dir.is_dir():
        return f"commondir target missing: {common_dir}"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: job_worktree_gitdir.py <worktree>", file=sys.stderr)
        return 2
    problem = linked_worktree_problem(argv[1])
    if problem is None:
        return 0
    print(f"FR #10245: broken job worktree: {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
