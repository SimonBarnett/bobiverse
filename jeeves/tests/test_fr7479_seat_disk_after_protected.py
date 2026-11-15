"""FR #7479: low free space after protected worktrees stay runs SeatDisk."""
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


def test_fr7479_script_chains_seat_disk_before_intake_warning():
    text = SCRIPT.read_text(encoding="utf-8")
    seat = text.find("FR #7479:")
    warn = text.find("still below MinFreeGB")
    assert seat != -1 and warn != -1 and seat < warn
    assert "Clear-BobiverseSeatDisk" in text
    assert "-Reclaim" in text
    assert "SkipSeatDisk" in text
    assert "hand-delete" in text.lower() or "protected worktrees stay" in text


@WIN
def test_fr7479_low_free_invokes_seat_disk_script(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    stub = tmp_path / "seat.ps1"
    marker = tmp_path / "seat-ran.txt"
    stub.write_text(
        "param([switch]$Reclaim, [double]$MinFreeGB)\r\n"
        "Set-Content -LiteralPath '%s' -Value $MinFreeGB -Encoding ascii\r\n" % marker,
        encoding="ascii",
    )
    base = tmp_path / "wt-base"
    base.mkdir()
    env = os.environ.copy()
    env["BOB_JOB_WORKTREE_BASE"] = str(base)
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
            "-MinFreeGB",
            "999",
            "-MaxExtraJobTrees",
            "99",
            "-SeatDiskScript",
            str(stub),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert marker.is_file(), out
    assert "FR #7479" in out
