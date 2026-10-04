"""Harvest #1581: large open GitHub counts are not proof the chair stopped assigning."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1581_monitor_diagnose_before_claiming_chair():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "#1581" in text
    assert "ungated_offerable" in text
    assert "!bored" in text
    assert "not" in text.lower() and "assigning" in text.lower()
    assert "must not" in text.lower() and "!assign" in text


def test_harvest1581_troubleshooting_row():
    text = TROUBLE.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    assert "#1581" in text
    assert "ungated_offerable" in text


def test_harvest1581_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1581" in text
    assert "ungated_offerable" in text