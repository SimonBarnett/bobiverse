"""FR #4864: SeatDisk reclaims nested .cursor/chats/<project>/<uuid> + bin *.old.

FR #4212 only deleted top-level project chat dirs by LastWriteTime. A live seat
keeps the project bucket fresh, shielding hundreds of MB of aged nested UUID
chat dirs (same class as FR #4226 nested grok sessions). SeatDisk must walk one
nested level, keep -KeepSessionId and fresh UUIDs, and when reclaiming also drop
~/.grok/bin/*.old backup binaries that no longer run.
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

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_seat_disk_script_pins_nested_cursor_and_bin_old():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    for needle in (
        "FR #4864",
        "aged nested .cursor/chats",
        "grok bin *.old",
        "KeepCursorHours",
        "KeepSessionId",
    ):
        assert needle in text, needle


def test_fr_skill_mentions_fr4864_nested_cursor_bin():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4864" in text or "#4864" in text
    assert "nested" in text.lower()
    assert ".cursor/chats" in text or "cursor/chats" in text


@WIN
def test_seat_disk_reclaims_aged_nested_cursor_uuids_and_bin_old(tmp_path: Path):
    grok = tmp_path / ".grok"
    (grok / "sessions").mkdir(parents=True)
    (grok / "downloads").mkdir()
    bin_dir = grok / "bin"
    bin_dir.mkdir()
    (bin_dir / "agent.exe").write_bytes(b"live-agent")
    (bin_dir / "agent.exe.old").write_bytes(b"0" * 4096)
    (bin_dir / "grok.exe.old").write_bytes(b"1" * 2048)

    chats = tmp_path / "cursor-chats"
    project = chats / "a3341a398b02770dec75cf04a2e2bca9"
    project.mkdir(parents=True)

    keep_id = "f8594bac-a271-4081-9eb0-8737271e15cb"
    keep = project / keep_id
    keep.mkdir()
    (keep / "live.txt").write_text("keep", encoding="utf-8")

    aged_id = "4776cb65-c5a6-4af5-97d3-f1bc0f18c2b8"
    aged = project / aged_id
    aged.mkdir()
    (aged / "big.bin").write_bytes(b"0" * 8192)

    fresh_id = "78ba00d5-02b6-4950-9b35-ba8e0d339fef"
    fresh = project / fresh_id
    fresh.mkdir()
    (fresh / "x.txt").write_text("fresh", encoding="utf-8")

    # Legacy flat project dir (no nested UUID) that is aged: still reclaim whole tree.
    flat_aged = chats / "old-flat-project"
    flat_aged.mkdir()
    (flat_aged / "old.bin").write_bytes(b"2" * 4096)

    old = time.time() - (48 * 3600)
    for path in (aged, flat_aged):
        os.utime(path, (old, old))
        for child in path.rglob("*"):
            os.utime(child, (old, old))

    # Project bucket looks fresh (live seat) — nested aged must still go.
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
    assert not aged.exists(), "aged nested .cursor/chats UUID must be reclaimed"
    assert keep.exists(), "KeepSessionId nested chat must stay"
    assert fresh.exists(), "fresh nested chat UUID must stay"
    assert project.exists(), "fresh project bucket must stay"
    assert not flat_aged.exists(), "aged flat project chat dir must be reclaimed"
    assert (bin_dir / "agent.exe").exists(), "live agent.exe must stay"
    assert not (bin_dir / "agent.exe.old").exists(), "agent.exe.old must be reclaimed"
    assert not (bin_dir / "grok.exe.old").exists(), "grok.exe.old must be reclaimed"
