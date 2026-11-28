"""FR #10245: broken linked job worktree metadata is reported, not silently used."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "common" / "scripts"))

from job_worktree_gitdir import linked_worktree_problem  # noqa: E402


def _linked(tmp_path: Path, *, with_head=True, with_gitdir=True, with_commondir=True) -> Path:
    common = tmp_path / "common" / ".git"
    meta = common / "worktrees" / "fr-1"
    meta.mkdir(parents=True)
    (common / "info").mkdir()
    if with_head:
        (meta / "HEAD").write_text("ref: refs/heads/fr-1\n", encoding="utf-8")
    if with_gitdir:
        (meta / "gitdir").write_text(str(tmp_path / "wt" / ".git") + "\n", encoding="utf-8")
    if with_commondir:
        (meta / "commondir").write_text("../..\n", encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {meta.as_posix()}\n", encoding="utf-8")
    return wt


def test_healthy_linked_worktree_passes(tmp_path):
    wt = _linked(tmp_path)
    assert linked_worktree_problem(wt) is None


def test_missing_head_is_reported(tmp_path):
    wt = _linked(tmp_path, with_head=False)
    problem = linked_worktree_problem(wt)
    assert problem and "HEAD" in problem


def test_missing_gitdir_and_commondir_are_reported(tmp_path):
    wt = _linked(tmp_path, with_gitdir=False, with_commondir=False)
    problem = linked_worktree_problem(wt)
    assert problem and "gitdir" in problem and "commondir" in problem


def test_gitfile_target_missing_is_reported(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: C:/nope/does/not/exist\n", encoding="utf-8")
    problem = linked_worktree_problem(wt)
    assert problem and "missing" in problem


def test_full_clone_is_not_flagged(tmp_path):
    (tmp_path / ".git").mkdir()
    assert linked_worktree_problem(tmp_path) is None


def test_cli_exit_codes(tmp_path):
    script = REPO / "common" / "scripts" / "job_worktree_gitdir.py"
    bad = _linked(tmp_path, with_head=False)
    r = subprocess.run([sys.executable, str(script), str(bad)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "broken job worktree" in r.stdout
