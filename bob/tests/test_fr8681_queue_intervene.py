"""BOB-43: stall path intervenes to keep the queue moving."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STALL = (ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobStallAlerts.ps1").read_text(encoding="utf-8")
WATCH = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
DOC = (ROOT / "bob" / "docs" / "bob-43-queue-intervene.md").read_text(encoding="utf-8")


def test_fr8681_queue_intervene_playbook():
    assert "function Invoke-BobQueueIntervene" in STALL
    assert "nudge-under-cap-fill" in STALL
    assert "queue-intervene.nudge" in STALL
    assert "Invoke-BobQueueIntervene" in WATCH
    assert "queue-intervene.nudge" in WATCH
    assert "queue-intervene action=" in WATCH or "queue-intervene action={0}" in STALL
    assert "BOB-43" in DOC
    assert "nudge-under-cap-fill" in DOC