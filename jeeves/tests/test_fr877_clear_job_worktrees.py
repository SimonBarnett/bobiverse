"""FR #877: Clear-BobiverseJobWorktrees.ps1 frees leftover FR/MRB temp worktrees."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_clear_job_worktrees_script_exists():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MinFreeGB" in text
    assert "KeepPath" in text
    assert "worktree remove" in text.lower() or "WorktreeRemove" in text
    assert "worktree prune" in text.lower() or "WorktreePrune" in text
    # UTF-8 no BOM
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


@WIN
def test_whatif_runs_and_prints_free_gb(tmp_path: Path):
    """WhatIf must not remove anything; must report FreeGB / KeepPath."""
    # Point RepoRoot at a throwaway git repo so we never touch the fleet install in this unit test.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    keep = tmp_path / "keep-me"
    keep.mkdir()
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
            "-KeepPath",
            str(keep),
            "-MinFreeGB",
            "0",
            "-WhatIf",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert "FreeGB" in out or "free" in out.lower()
    assert keep.is_dir()


def test_job_fr_skill_documents_worktree_cleanup():
    skill = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "Clear-BobiverseJobWorktrees" in text or "worktree remove" in text.lower()
    assert "FreeGB" in text or "MinFreeGB" in text or "2" in text
