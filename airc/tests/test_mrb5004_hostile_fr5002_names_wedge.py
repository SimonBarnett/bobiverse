"""Hostile pin for FR #5002 / MRB #5004: multiclient NAMES + auth-wedge needles.

Pins contiguous service / remote / irc_agent phrases so a later keep-both cannot
drop the reattach preserve-NAMES path or NSSM exit recovery.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
REMOTE = (ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1").read_text(encoding="utf-8")
AGENT = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
CONSOLE = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")


def test_service_pins_no_clear_on_join_and_watchdogs():
    assert "do NOT clear the member map here" in SERVICE
    assert 'self.send(f"NAMES {self.channel}")' in SERVICE or 'f"NAMES {self.channel}"' in SERVICE
    assert "NAMES_SYNC_WATCH_S" in SERVICE
    assert "AUTH_WEDGE_EXIT_S" in SERVICE
    assert "_exit_for_nssm_restart" in SERVICE
    assert "def _names_sync_watchdog(" in SERVICE
    assert "def _auth_wedge_watchdog(" in SERVICE
    assert "return 1" in SERVICE


def test_deny_reply_and_remote_fail_fast_pins():
    assert "exit=126" in CONSOLE
    assert "DONE id=" in CONSOLE or 'f"DONE id=' in CONSOLE
    assert "exit=126" in REMOTE
    assert "DONE" in AGENT
