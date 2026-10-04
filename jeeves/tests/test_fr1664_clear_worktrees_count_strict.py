"""FR #1664: Clear-BobiverseJobWorktrees StrictMode .Count on scalar Sort-Object result."""
from __future__ import annotations

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


def test_script_wraps_sorted_jobtrees_before_count():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #1664" in text
    assert "FR #1740" in text
    assert "Set-StrictMode" in text
    # Must force array before Sort-Object .Count (scalar path is the bug class).
    assert "$sorted = @(" in text or "$sorted=@(" in text.replace(" ", "")
    assert "@($jobTrees" in text.replace(" ", "") or "jobTrees = @(" in text
    assert "List[string]" in text or "ToArray()" in text


@WIN
def test_force_with_single_job_worktree_does_not_throw_count(tmp_path: Path):
    """Reproduce ionos/marchhare: one job tree + MaxExtraJobTrees=0 + StrictMode .Count."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    # Linked worktree named like a job tree (single path → Sort-Object scalar before fix).
    wt = tmp_path / "bobiverse-fr1664-wt"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fr-1664-test", str(wt)],
        check=True,
        capture_output=True,
    )
    keep = tmp_path / "keep-main"
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
            "999",
            "-MaxExtraJobTrees",
            "0",
            "-Force",
            "-WhatIf",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "PropertyNotFoundStrict" not in out
    assert "property 'Count'" not in out.lower()
    assert "FreeGB" in out
    # Cleanup linked tree so tmp_path can delete.
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
        capture_output=True,
    )


@WIN
def test_fr1740_force_with_zero_job_worktrees_does_not_throw_count(tmp_path: Path):
    """FR #1740: only the install worktree listed — StrictMode must tolerate .Count of empty job set."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    keep = tmp_path / "keep-main"
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
            "999",
            "-MaxExtraJobTrees",
            "0",
            "-Force",
            "-WhatIf",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "PropertyNotFoundStrict" not in out
    assert "property 'Count'" not in out.lower()
    assert "removing 0 job worktree" in out.lower() or "removing 0" in out.lower()
