"""FR #4192: after JobWorktrees leaves FreeGB low, seats must run SeatDisk.

Clear-BobiverseJobWorktrees removed=0 still leaves C: under MinFreeGB when
~/.grok sessions and user %TEMP% caches dominate. WARN must name
Clear-BobiverseSeatDisk -Reclaim; SeatDisk must reclaim aged user-TEMP
bobiverse/pytest dirs; FR skill must run SeatDisk before filing intake.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEAT = REPO / "common" / "scripts" / "Clear-BobiverseSeatDisk.ps1"
JOBS = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_job_worktrees_warn_names_seat_disk():
    text = JOBS.read_text(encoding="utf-8")
    assert "Clear-BobiverseSeatDisk" in text
    assert "FR #4192" in text or "4192" in text
    assert "-Reclaim" in text


def test_fr_skill_runs_seat_disk_before_intake():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "Clear-BobiverseSeatDisk" in text
    assert "FR #4192" in text or "#4192" in text
    # Must not jump straight to intake while SeatDisk is the next step.
    assert "-Reclaim" in text


def test_seat_disk_script_covers_user_temp_patterns():
    text = SEAT.read_text(encoding="utf-8")
    for needle in (
        "TempRoot",
        "pytest-of-",
        "bobiverse-",
        "KeepTempHours",
        "FR #4192",
    ):
        assert needle in text, needle


@WIN
def test_seat_disk_reclaims_aged_user_temp_dirs(tmp_path: Path):
    grok = tmp_path / ".grok"
    (grok / "sessions").mkdir(parents=True)
    (grok / "downloads").mkdir()
    temp = tmp_path / "Temp"
    aged = temp / "pytest-of-Administrator"
    aged.mkdir(parents=True)
    (aged / "big.bin").write_bytes(b"0" * 4096)
    keep = temp / "pytest-of-keep-fresh"
    keep.mkdir()
    (keep / "x.txt").write_text("fresh", encoding="utf-8")
    # Age the reclaim candidate; leave keep fresh.
    import os
    import time

    old = time.time() - (48 * 3600)
    os.utime(aged, (old, old))
    for child in aged.rglob("*"):
        os.utime(child, (old, old))

    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SEAT),
            "-GrokHome",
            str(grok),
            "-AiRoot",
            str(tmp_path / "ai"),
            "-TempRoot",
            str(temp),
            "-MinFreeGB",
            "1000",
            "-KeepTempHours",
            "24",
            "-KeepSessionHours",
            "6",
            "-Reclaim",
            "-Force",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert "FreeGB" in out
    assert not aged.exists(), "aged pytest-of-* must be reclaimed"
    assert keep.exists(), "fresh TEMP dir must stay"
