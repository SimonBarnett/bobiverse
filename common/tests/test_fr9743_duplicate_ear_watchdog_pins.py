"""FR #9743: tray / monitor / docs pin Running-duplicate detection."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr9743_tray_hover_running_duplicate():
    text = (ROOT / "bob/tray/src/Public/Get-BobTrayHover.ps1").read_text(encoding="utf-8")
    assert "Running-duplicate" in text
    assert "FR #9743" in text or "9743" in text
    assert "$child -gt 1" in text


def test_fr9743_tray_watchdog_detect_duplicate():
    text = (ROOT / "bob/tray/dialogs/BobTray.cs").read_text(encoding="utf-8")
    assert "DetectDuplicateBobEar" in text
    assert "ircbob-duplicate-ear" in text
    assert "9743" in text


def test_fr9743_monitor_running_duplicate_finding():
    text = (ROOT / "jeeves/tools/monitor/ircbob_ear.py").read_text(encoding="utf-8")
    assert "Running-duplicate" in text
    assert "_ear_child_count" in text
    assert "9743" in text


def test_fr9743_bob_ear_doc_mentions_lock_and_live_irc():
    text = (ROOT / "bob/docs/bob-ear.md").read_text(encoding="utf-8")
    assert "FR #9743" in text
    assert "ear.<nick>.lock" in text or "`ear.<nick>.lock`" in text
    assert "outbox.txt.pos" in text
