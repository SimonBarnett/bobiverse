"""FR #4226: SeatDisk reclaims aged nested ~/.grok/sessions/<cwd>/<uuid>.

Grok Build nests session UUID dirs under a cwd-encoded bucket
(e.g. sessions/C%3A%5Cai%5Cbob%5Cworker/<guid>/). Top-level-only reclaim
skips aged UUIDs when the cwd bucket stays fresh from the live seat,
leaving ~1GB on C: after SeatDisk. Reclaim must walk one level of nested
UUID dirs, keep -KeepSessionId, keep fresh UUIDs, and still support the
legacy flat sessions/<guid> layout.
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


def test_seat_disk_script_pins_nested_sessions_fr4226():
    raw = SEAT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    for needle in (
        "FR #4226",
        "aged nested grok session",
        "KeepSessionId",
        "KeepSessionHours",
    ):
        assert needle in text, needle


def test_fr_skill_mentions_fr4226_nested_sessions():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4226" in text or "#4226" in text
    assert "nested" in text.lower() or "cwd" in text.lower()


@WIN
def test_seat_disk_reclaims_aged_nested_session_uuids(tmp_path: Path):
    grok = tmp_path / ".grok"
    cwd_bucket = grok / "sessions" / "C%3A%5Cai%5Cbob%5Cworker"
    cwd_bucket.mkdir(parents=True)

    keep_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    keep = cwd_bucket / keep_id
    keep.mkdir()
    (keep / "live.txt").write_text("keep", encoding="utf-8")

    aged_id = "11111111-2222-3333-4444-555555555555"
    aged = cwd_bucket / aged_id
    aged.mkdir()
    (aged / "big.bin").write_bytes(b"0" * 8192)

    fresh_id = "99999999-8888-7777-6666-555555555555"
    fresh = cwd_bucket / fresh_id
    fresh.mkdir()
    (fresh / "x.txt").write_text("fresh", encoding="utf-8")

    # Legacy flat session (also aged) must still reclaim.
    flat_aged = grok / "sessions" / "abcdef01-2345-6789-abcd-ef0123456789"
    flat_aged.mkdir()
    (flat_aged / "old.bin").write_bytes(b"1" * 4096)

    old = time.time() - (48 * 3600)
    for path in (aged, flat_aged):
        os.utime(path, (old, old))
        for child in path.rglob("*"):
            os.utime(child, (old, old))

    # Cwd bucket itself looks fresh (live seat touches it) ? nested aged must still go.
    now = time.time()
    os.utime(cwd_bucket, (now, now))

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
            str(tmp_path / "cursor-chats"),
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
    assert not aged.exists(), "aged nested UUID under cwd bucket must be reclaimed"
    assert keep.exists(), "KeepSessionId nested UUID must stay"
    assert fresh.exists(), "fresh nested UUID must stay"
    assert not flat_aged.exists(), "legacy flat aged session must still reclaim"
    assert cwd_bucket.exists(), "cwd bucket with remaining sessions must stay"
