"""FR #4212: SeatDisk reclaims aged ~/.cursor/chats + CRITICAL size report.

After JobWorktrees removed=0 and SeatDisk Temp/sessions reclaim, C: can still
sit near 0 FreeGB because aged ~/.cursor/chats children (hundreds of MB) were
never in the reclaim set. SeatDisk must accept -KeepCursorHours /
-CursorChatsRoot, reclaim aged chat dirs, and when FreeGB stays under
MinFreeGB print a CRITICAL ranked consumers report. JobWorktrees WARN and the
FR skill must cite FR #4212.
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
JOBS = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_seat_disk_script_pins_cursor_and_critical():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    for needle in (
        "KeepCursorHours",
        "CursorChatsRoot",
        "FR #4212",
        "CRITICAL remaining consumers",
        ".cursor/chats",
    ):
        assert needle in text, needle


def test_job_worktrees_warn_cites_fr4212_and_cursor_chats():
    text = JOBS.read_text(encoding="utf-8")
    assert "FR #4212" in text or "4212" in text
    assert ".cursor/chats" in text or "cursor/chats" in text
    assert "Clear-BobiverseSeatDisk" in text


def test_fr_skill_mentions_fr4212_cursor_critical():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4212" in text or "#4212" in text
    assert "KeepCursorHours" in text or ".cursor/chats" in text
    assert "CRITICAL" in text


@WIN
def test_seat_disk_reclaims_aged_cursor_chats(tmp_path: Path):
    grok = tmp_path / ".grok"
    (grok / "sessions").mkdir(parents=True)
    (grok / "downloads").mkdir()
    chats = tmp_path / "cursor-chats"
    aged = chats / "old-project-chat"
    aged.mkdir(parents=True)
    (aged / "big.bin").write_bytes(b"0" * 8192)
    fresh = chats / "fresh-chat"
    fresh.mkdir()
    (fresh / "x.txt").write_text("fresh", encoding="utf-8")

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
            "-CursorChatsRoot",
            str(chats),
            "-TempRoot",
            str(tmp_path / "Temp"),
            "-MinFreeGB",
            "1000",
            "-KeepCursorHours",
            "24",
            "-KeepSessionHours",
            "6",
            "-KeepTempHours",
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
    assert "FreeGB" in out
    assert "CRITICAL remaining consumers" in out
    assert not aged.exists(), "aged .cursor/chats child must be reclaimed"
    assert fresh.exists(), "fresh cursor chat dir must stay"
