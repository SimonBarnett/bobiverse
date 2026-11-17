"""FR #4197: Clear-BobiverseJobWorktrees must not abort when one worktree .git is missing.

A registered job tree whose .git file/dir is gone must not abort the Clear run
(FR #4197). FR #8023: keep that tree as unknown (no hand-delete), warn, continue,
and still reclaim later safe trees.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_fr4197_script_continues_on_missing_git_markers():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #4197" in text
    # Must catch terminating NativeCommandError / missing .git — not only stringify.
    assert "try" in text.lower() and "catch" in text.lower()
    assert ".git" in text
    assert "continue" in text


def test_fr4197_skill_documents_continue_on_broken_registration():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "Clear-BobiverseJobWorktrees" in text
    assert "FR #4197" in text or "#4197" in text


@WIN
def test_fr4197_clear_continues_after_missing_git_worktree(tmp_path: Path):
    """Broken .git on one tree must not leave a second reclaimable tree behind."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    wt_broken = tmp_path / "bobiverse-fr4197-broken"
    wt_good = tmp_path / "bobiverse-fr4197-good"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fr-4197-b", str(wt_broken)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fr-4197-g", str(wt_good)],
        check=True,
        capture_output=True,
    )
    # Corrupt: path remains registered but .git is gone (live failure class).
    git_marker = wt_broken / ".git"
    assert git_marker.exists()
    git_marker.unlink() if git_marker.is_file() else shutil.rmtree(git_marker)
    assert not git_marker.exists()

    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(repo),
            "-Force",
            "-MinFreeGB",
            "1000",
            "-SkipSeatDisk",
            "-MaxExtraJobTrees",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "FR #4197" in out or "missing" in out.lower() or "does not exist" in out.lower()
    # FR #8023: broken .git is kept as unknown; Clear continues and reclaims the good tree.
    assert not wt_good.exists(), "second worktree must still be removed after broken .git"
    assert wt_broken.exists(), "missing-.git tree must be kept (unknown), not hand-deleted"
