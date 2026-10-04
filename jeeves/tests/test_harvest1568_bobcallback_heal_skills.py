"""Harvest #1568: BobCallback supervised single-owner heal playbook in Jeeves skills."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path


def _no_conflict_markers(text: str) -> None:
    for line in text.splitlines():
        if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> "):
            raise AssertionError(f"conflict marker: {line!r}")
        if line == "=======":
            raise AssertionError("conflict marker: =======")


def test_harvest1568_troubleshooting_bobcallback_heal_section():
    text = TROUBLE.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    _no_conflict_markers(text)
    assert "BobCallback heal" in text
    assert "Start-BobCallbackSupervised" in text
    assert "Never stack" in text or "never stack" in text.lower()
    assert "Exclude heal" in text or "exclude current `$PID`" in text.lower() or "exclude current $PID" in text.lower()
    assert "60s" in text or "60 s" in text
    assert "Do not kill the supervised parent" in text or "never kill the supervised" in text.lower()
    assert "digest.lock" in text


def test_harvest1568_monitor_points_at_single_owner_heal():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    _no_conflict_markers(text)
    assert "BobCallback single-owner heal" in text
    assert "#1568" in text
    assert "Start-BobCallbackSupervised" in text
    assert "bobiverse-jeeves-troubleshooting" in text


def test_harvest1568_skill_harvest_log_line():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1568" in text
    assert "BobCallback" in text
    assert "Start-BobCallbackSupervised" in text
