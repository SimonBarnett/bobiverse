"""Harvest #1706: BobCallback LISTEN+timeout re-probe; skill-offer ungated expected."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1706_monitor_timeout_and_skill_offer():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "1706" in text
    assert "timeout" in text.lower()
    assert "LISTEN" in text
    assert "ungated_offerable" in text or "skill-offer" in text.lower() or "Skill-offer" in text


def test_harvest1706_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1706" in text