"""FR #890: Clear-BobiverseSeatDisk.ps1 reclaims non-worktree seat disk headroom."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseSeatDisk.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_seat_disk_script_exists_and_is_utf8_no_bom():
    assert SCRIPT.is_file()
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    for needle in (
        "MinFreeGB",
        "KeepSessionId",
        "sessions",
        "downloads",
        "WhatIf",
        "FreeGB",
    ):
        assert needle in text, needle


@WIN
def test_report_only_whatif_runs(tmp_path: Path):
    # Isolate HOME-like roots under tmp so we never delete real seat data in CI/unit.
    grok = tmp_path / ".grok"
    (grok / "sessions" / "old-session").mkdir(parents=True)
    (grok / "sessions" / "old-session" / "x.txt").write_text("x", encoding="utf-8")
    (grok / "downloads").mkdir()
    (grok / "downloads" / "grok-fake.exe").write_bytes(b"0" * 1024)
    (grok / "pr-merge-clones" / "repo").mkdir(parents=True)
    ai = tmp_path / "ai"
    (ai / "backup-old-20260101").mkdir(parents=True)

    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-GrokHome",
            str(grok),
            "-AiRoot",
            str(ai),
            "-MinFreeGB",
            "1000",
            "-KeepSessionId",
            "keep-me",
            "-WhatIf",
            "-Reclaim",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert "FreeGB" in out
    # WhatIf must not delete
    assert (grok / "downloads" / "grok-fake.exe").is_file()
    assert (grok / "sessions" / "old-session").is_dir()


def test_worker_seat_skill_mentions_seat_disk():
    skill = (
        REPO
        / "bob"
        / "agents"
        / "worker"
        / ".grok"
        / "skills"
        / "bobiverse-worker-seat"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "Clear-BobiverseSeatDisk" in text or "SeatDisk" in text
