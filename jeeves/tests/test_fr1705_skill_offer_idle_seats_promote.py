"""Harvest #1705: skill-offer idle_seats expected + callback timeout recover."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
TR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1705_monitor_skill_flood_expected():
    text = MON.read_text(encoding="utf-8")
    assert "1705" in text or "1682" in text
    assert "ungated" in text.lower() or "skill-offer" in text.lower() or "skill flood" in text.lower() or "Skill-offer" in text


def test_fr1705_troubleshooting_reprobe():
    text = TR.read_text(encoding="utf-8")
    assert "re-probe" in text.lower() or "reprobe" in text.lower()
    assert "LISTEN" in text


def test_fr1705_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1705" in text
    assert "<<<<<<" not in text


def test_fr1705_files_end_with_newline():
    for p in (MON, TR, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
