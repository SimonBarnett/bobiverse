"""FR #9309: prefer tip Sync with sync-monitor-force over stale J:\\scripts Sync.

Composed drive-root installs (J: -> \\\\walrus\\Jeeves) kept an Oct-2026 Sync
beside Start-JeevesMonitor that lacked sync-monitor-force. Resolve preferred
that flat copy, so opencode_seats.py (FR #8583) never landed on tools\\monitor.
"""
from __future__ import annotations

from repo_layout import REPO

START = REPO / "jeeves" / "scripts" / "Start-JeevesMonitor.ps1"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
DOCS = REPO / "jeeves" / "docs" / "monitoring.md"
OC = REPO / "jeeves" / "tools" / "monitor" / "opencode_seats.py"
OC_PS1 = REPO / "jeeves" / "scripts" / "Test-JeevesMonitorOpencodeSeats.ps1"


def test_fr9309_opencode_seats_shipped_in_repo():
    assert OC.is_file(), "opencode_seats.py must ship under jeeves/tools/monitor"
    assert OC_PS1.is_file(), "Test-JeevesMonitorOpencodeSeats.ps1 must ship"


def test_fr9309_start_prefers_tip_sync_with_monitor_force():
    text = START.read_text(encoding="utf-8-sig")
    assert "FR #9309" in text
    assert "sync-monitor-force" in text
    # Bob tip common\\scripts before composed ScriptRoot flat copy.
    bob_common = text.find("Join-Path $BobRoot ('common\\scripts\\'")
    script_root = text.find("Join-Path $ScriptRoot $name")
    assert bob_common >= 0, "BobRoot common\\scripts candidate missing"
    assert script_root >= 0, "ScriptRoot candidate missing"
    assert bob_common < script_root, "Bob tip Sync must be preferred over ScriptRoot flat Sync"


def test_fr9309_invoke_prefers_tip_sync_and_resolves_drive_root_bob():
    text = INVOKE.read_text(encoding="utf-8-sig")
    assert "FR #9309" in text
    assert "sync-monitor-force" in text
    assert "Resolve-BobInstallRootFromJeeves" in text or "SystemDrive" in text
    # Must not only use Split-Path -Parent of J:\\ (empty on drive root).
    assert "C:\\ai\\bob" in text or "ai\\bob" in text


def test_fr9309_sync_still_force_copies_monitor():
    text = SYNC.read_text(encoding="utf-8-sig")
    assert "sync-monitor-force" in text
    assert "FR #8860" in text


def test_fr9309_docs_name_stale_flat_sync_trap():
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #9309" in text
    assert "sync-monitor-force" in text
    assert "opencode_seats" in text
