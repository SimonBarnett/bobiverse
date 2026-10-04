"""FR #1661: prune job worktrees earlier — cap extras even when FreeGB >= MinFreeGB."""
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


def test_fr1661_script_has_earlier_prune_gate():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #1661" in text
    assert "MaxExtraJobTrees" in text
    # Soft hygiene must not early-return solely because FreeGB >= MinFreeGB.
    assert "earlier prune" in text.lower() or "soft cap" in text.lower() or "even when FreeGB" in text
    # StrictMode-safe arrays (also FR #1664 class).
    assert "$sorted = @(" in text or "$sorted=@(" in text.replace(" ", "")
    assert "@($paths | Where-Object" in text or "@($jobTrees" in text


def test_fr1661_skill_documents_earlier_cap():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "Clear-BobiverseJobWorktrees" in text
    assert "MaxExtraJobTrees" in text
    # FR #1661: seats must know the soft cap runs without waiting for FreeGB < 2.
    assert "FR #1661" in text


@WIN
def test_fr1661_soft_cap_runs_when_free_above_min(tmp_path: Path):
    """With FreeGB artificially above MinFreeGB (MinFreeGB=0), still remove extras beyond MaxExtraJobTrees."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    wt_a = tmp_path / "bobiverse-fr1661a-wt"
    wt_b = tmp_path / "bobiverse-fr1661b-wt"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fr-1661-a", str(wt_a)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", "fr-1661-b", str(wt_b)],
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
            # MinFreeGB=0 => FreeGB is never "low"; soft cap must still fire (FR #1661).
            "-MinFreeGB",
            "0",
            "-MaxExtraJobTrees",
            "0",
            "-WhatIf",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "PropertyNotFoundStrict" not in out
    assert "OK: free space above MinFreeGB" not in out  # must not early-return past soft cap
    assert "WhatIf" in out and "worktree remove" in out.lower()
    for wt in (wt_a, wt_b):
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
            capture_output=True,
        )
