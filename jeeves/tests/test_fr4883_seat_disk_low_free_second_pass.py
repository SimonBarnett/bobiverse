"""FR #4883: when FreeGB stays under MinFreeGB, second-pass reclaim.

After nested cursor + bin *.old (FR #4864), marchhare still sat at FreeGB~1.98
with identical agent.exe/grok.exe twins (~161MB each) and nested chats aged
under KeepCursorHours=24. When still under MinFreeGB, SeatDisk must:
- hardlink-dedupe identical agent.exe/grok.exe (keep both names, one extent)
- reclaim nested .cursor/chats with KeepCursorHoursLow (default 6)
"""
from __future__ import annotations

import hashlib
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

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_seat_disk_script_pins_fr4883_second_pass():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert all(ord(c) < 128 for c in text), "SeatDisk.ps1 must stay BOM-less ASCII"
    for needle in (
        "FR #4883",
        "KeepCursorHoursLow",
        "agent.exe",
        "grok.exe",
        "hardlink",
        "aged nested .cursor/chats (low)",
    ):
        assert needle in text, needle


def test_fr_skill_mentions_fr4883():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4883" in text or "#4883" in text


@WIN
def test_seat_disk_second_pass_hardlink_and_low_cursor(tmp_path: Path):
    grok = tmp_path / ".grok"
    (grok / "sessions").mkdir(parents=True)
    (grok / "downloads").mkdir()
    bin_dir = grok / "bin"
    bin_dir.mkdir()
    payload = b"IDENTICAL-AGENT-GROK-" + (b"0" * 4096)
    (bin_dir / "agent.exe").write_bytes(payload)
    (bin_dir / "grok.exe").write_bytes(payload)
    assert (bin_dir / "agent.exe").stat().st_size == (bin_dir / "grok.exe").stat().st_size

    chats = tmp_path / "cursor-chats"
    project = chats / "proj-live"
    project.mkdir(parents=True)
    keep_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    keep = project / keep_id
    keep.mkdir()
    (keep / "live.txt").write_text("keep", encoding="utf-8")
    aged_id = "11111111-2222-3333-4444-555555555555"
    aged = project / aged_id
    aged.mkdir()
    (aged / "big.bin").write_bytes(b"9" * 8192)

    # Nested aged 12h (under 24h KeepCursorHours, over KeepCursorHoursLow=6).
    mid = time.time() - (12 * 3600)
    os.utime(aged, (mid, mid))
    for child in aged.rglob("*"):
        os.utime(child, (mid, mid))
    now = time.time()
    os.utime(project, (now, now))

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
            str(tmp_path / "Temp"),
            "-CursorChatsRoot",
            str(chats),
            "-MinFreeGB",
            "1000",
            "-KeepSessionId",
            keep_id,
            "-KeepSessionHours",
            "6",
            "-KeepTempHours",
            "24",
            "-KeepCursorHours",
            "24",
            "-KeepCursorHoursLow",
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
    assert not aged.exists(), "12h nested chat must fall to KeepCursorHoursLow pass"
    assert keep.exists(), "KeepSessionId nested chat must stay"
    assert project.exists()
    assert (bin_dir / "agent.exe").exists()
    assert (bin_dir / "grok.exe").exists(), "grok.exe name must remain (hardlink)"
    # Same content; on NTFS hardlink, size on disk is shared (both paths exist).
    ha = hashlib.sha256((bin_dir / "agent.exe").read_bytes()).hexdigest()
    hg = hashlib.sha256((bin_dir / "grok.exe").read_bytes()).hexdigest()
    assert ha == hg
    assert "hardlink" in out.lower() or "dedupe" in out.lower() or "twin" in out.lower()
