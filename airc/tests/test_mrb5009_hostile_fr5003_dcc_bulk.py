"""Hostile pin for FR #5003 / MRB #5009: reverse DCC bulk needles.

Pins contiguous module / DONE / keep-both phrases so a later fold cannot drop
reverse DCC or the FR #5002 optional-id DONE regex.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DCC = (ROOT / "airc" / "scripts" / "airc_dcc_bulk.py").read_text(encoding="utf-8")
CONSOLE = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
REMOTE = (ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1").read_text(encoding="utf-8")


def test_dcc_module_and_control_plane_pins():
    assert "DCCLISTEN" in DCC
    assert "def reverse_dcc_roundtrip_localhost" in DCC or "reverse_dcc" in DCC
    assert "via=dcc" in DCC
    assert "prefer_dcc_bulk" in CONSOLE or "dcc_peer_ready" in CONSOLE
    assert "note_dcclisten" in CONSOLE


def test_shell_id_re_keeps_5002_and_5003():
    assert "NAMES_SYNC_WATCH_S" in SERVICE
    assert "AUTH_WEDGE_EXIT_S" in SERVICE
    assert "id=([0-9a-f]+)\\s+)?" in SERVICE.replace("\n", "") or "(?:id=" in SERVICE
    assert "bytes=" in SERVICE or "via=dcc" in REMOTE
    assert "via=dcc" in REMOTE
    assert "exit=126" in REMOTE
