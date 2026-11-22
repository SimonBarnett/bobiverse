"""FR #8860: composed jeeves tools/monitor is force-copied from tip on Sync."""
from __future__ import annotations

from repo_layout import REPO

SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
START = REPO / "jeeves" / "scripts" / "Start-JeevesMonitor.ps1"
DOCS = REPO / "jeeves" / "docs" / "monitoring.md"


def test_sync_force_copies_jeeves_monitor():
    text = SYNC.read_text(encoding="utf-8-sig")
    assert "sync-monitor-force" in text
    assert "FR #8860" in text
    assert "tools\\monitor" in text
    # Whole tools\\ stays /XO (MRB #6162); only monitor is force-copied.
    assert "Jeeves tools\\ keep /XO" in text or "keep /XO" in text


def test_start_monitor_refreshes_when_sync_script_present():
    text = START.read_text(encoding="utf-8-sig")
    assert "Sync-BobiverseFromRepo.ps1" in text
    assert "FR #8860" in text
    assert "-Product jeeves" in text
    assert "-InstallRoot $InstallRoot" in text


def test_monitoring_doc_names_drive_root_sync():
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #8860" in text
    assert "sync-monitor-force" in text
    assert "-Product jeeves" in text
