"""FR #5154: when FreeGB stays under MinFreeGB, third-pass TEMP reclaim.

Marchhare still had user Temp ~1.26GB after FR #4883. SeatDisk must apply
KeepTempHoursLow (default 6) to known leftover dirs plus extra pip/pytest
names, and age Windows\\Temp files faster. Never wipe vscode/Outlook trees.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEAT = REPO / "common" / "scripts" / "Clear-BobiverseSeatDisk.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_seat_disk_script_pins_fr5154_temp_low_pass():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert all(ord(c) < 128 for c in text), "SeatDisk.ps1 must stay BOM-less ASCII"
    for needle in (
        "FR #5154",
        "KeepTempHoursLow",
        "pip-build-",
        "pip-install-",
        "pytest-*",
        "aged user-TEMP (low)",
    ):
        assert needle in text, needle
    assert "vscode" in text.lower() or "never wipe" in text.lower()


def test_fr_and_fleet_skills_mention_fr5154():
    fr = FR_SKILL.read_text(encoding="utf-8")
    fleet = FLEET.read_text(encoding="utf-8")
    assert "FR #5154" in fr or "#5154" in fr
    assert "KeepTempHoursLow" in fr
    assert "5154" in fleet


@WIN
def test_seat_disk_low_pass_drops_12h_pip_keeps_vscode(tmp_path: Path):
    grok = tmp_path / ".grok"
    (grok / "sessions").mkdir(parents=True)
    (grok / "downloads").mkdir()
    (grok / "bin").mkdir()
    temp = tmp_path / "Temp"
    temp.mkdir()
    pip = temp / "pip-build-abc123"
    pip.mkdir()
    (pip / "wheel.bin").write_bytes(b"1" * 4096)
    pytest_dir = temp / "pytest-of-old"
    pytest_dir.mkdir()
    (pytest_dir / "c.bin").write_bytes(b"2" * 4096)
    vscode = temp / "vscode-userdata"
    vscode.mkdir()
    (vscode / "keep.txt").write_text("do-not-delete", encoding="utf-8")
    mid = time.time() - (12 * 3600)
    for d in (pip, pytest_dir, vscode):
        os.utime(d, (mid, mid))
        for child in d.rglob("*"):
            os.utime(child, (mid, mid))

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
            "-CursorChatsRoot",
            str(tmp_path / "cursor-chats"),
            "-MinFreeGB",
            "1000",
            "-KeepSessionHours",
            "6",
            "-KeepTempHours",
            "24",
            "-KeepTempHoursLow",
            "6",
            "-KeepCursorHours",
            "24",
            "-Reclaim",
            "-Force",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert "FR #5154" in out or "KeepTempHoursLow" in out
    assert not pip.exists(), "12h pip-build must fall to KeepTempHoursLow pass"
    assert not pytest_dir.exists(), "12h pytest-of must fall to low pass"
    assert vscode.exists(), "vscode-* must stay (not a seat leftover pattern)"
