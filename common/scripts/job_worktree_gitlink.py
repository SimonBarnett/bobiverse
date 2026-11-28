"""FR #10253: detect and repair a linked job worktree whose ``.git`` gitfile is broken.

A linked worktree has a ``.git`` *file* (``gitdir: <common>/worktrees/<name>``).
When that admin directory is missing from the install root, every git command
in the job tree fails with "gitfile does not point to a valid repository".

``gitlink_problem`` reports the first broken link (``None`` when healthy).
``repair_gitlink`` recreates only the admin directory (HEAD, commondir, gitdir)
and runs ``git reset -q`` (mixed; never ``checkout``) to rebuild the index. The
working tree and untracked files are never touched.

CLI:
  python common/scripts/job_worktree_gitlink.py --check <worktree>
  python common/scripts/job_worktree_gitlink.py --repair <worktree> --branch fr-N
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _read_gitfile_target(wt: Path) -> Path | None:
    gitfile = wt / ".git"
    try:
        raw = gitfile.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw.lower().startswith("gitdir:"):
        return None
    target = Path(raw.split(":", 1)[1].strip())
    if not target.is_absolute():
        target = (wt / target).resolve()
    return target


def gitlink_problem(worktree: str | Path) -> str | None:
    """Return None when the worktree's gitfile resolves; else a short problem tag."""
    wt = Path(worktree)
    git = wt / ".git"
    if git.is_dir():
        return None
    if not git.exists():
        return "git-missing"
    admin = _read_gitfile_target(wt)
    if admin is None:
        return "gitfile-unparsable"
    if not admin.is_dir():
        return f"gitdir-missing:{admin}"
    commondir = admin / "commondir"
    if not commondir.is_file():
        return "commondir-missing"
    try:
        common = (admin / commondir.read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        return "commondir-unreadable"
    if not common.is_dir():
        return f"common-missing:{common}"
    if not (admin / "HEAD").is_file():
        return "head-missing"
    return None


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )


def repair_gitlink(worktree: str | Path, *, branch: str) -> str:
    """Recreate a missing admin dir for *worktree*.

    Returns ``ok`` (already healthy), ``repaired``, or ``refused:<reason>``.
    Only the ``gitdir-missing`` case is repaired; the common git dir must
    already exist, and *branch* must be named explicitly.
    """
    wt = Path(worktree).resolve()
    problem = gitlink_problem(wt)
    if problem is None:
        return "ok"
    if not problem.startswith("gitdir-missing:"):
        return f"refused:{problem}"
    branch = (branch or "").strip()
    if not branch or branch.startswith("-"):
        return "refused:branch-required"
    admin = Path(problem.split(":", 1)[1])
    # admin = <common>/worktrees/<name>; the common dir is two levels up.
    common = admin.parent.parent
    if admin.parent.name != "worktrees" or not (common / "objects").is_dir():
        return "refused:common-dir-unexpected"
    if _git(common, "rev-parse", "--git-dir").returncode != 0:
        return "refused:common-dir-not-git"
    if _git(common, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode != 0:
        return "refused:branch-not-found"

    admin.mkdir(parents=True, exist_ok=True)
    (admin / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8", newline="\n")
    (admin / "commondir").write_text("../..\n", encoding="utf-8", newline="\n")
    (admin / "gitdir").write_text(str(wt / ".git") + "\n", encoding="utf-8", newline="\n")
    reset = _git(wt, "reset", "-q")
    if reset.returncode != 0:
        return f"refused:reset-failed:{reset.stderr.strip()[:200]}"
    if gitlink_problem(wt) is not None:
        return f"refused:still-broken:{gitlink_problem(wt)}"
    return "repaired"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", metavar="WORKTREE")
    mode.add_argument("--repair", metavar="WORKTREE")
    ap.add_argument("--branch", default="")
    args = ap.parse_args(argv)
    if args.check:
        problem = gitlink_problem(args.check)
        print(problem or "ok")
        return 0 if problem is None else 1
    status = repair_gitlink(args.repair, branch=args.branch)
    print(status)
    return 0 if status in ("ok", "repaired") else 1


if __name__ == "__main__":
    sys.exit(main())
