"""Harvest #1665: post-DONE harvest_hold is not starve."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
WORKER = ROOT / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1665_monitor_harvest_hold_not_starve():
    text = MON.read_text(encoding="utf-8")
    assert "harvest_hold" in text or "harvest hold" in text.lower()
    assert "1665" in text or "not starve" in text.lower()
    assert "90" in text
    assert "Post-DONE harvest_hold is not starve" in text


def test_fr1665_worker_mentions_hold():
    text = WORKER.read_text(encoding="utf-8")
    assert "harvest hold" in text.lower() or "harvest_hold" in text
    assert "90" in text or "HARVEST_HOLD" in text
    assert "1665" in text or "not" in text.lower()


def test_fr1665_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1665" in text
    assert "<<<<<<" not in text


def test_fr1665_files_end_with_newline():
    for p in (MON, WORKER, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
