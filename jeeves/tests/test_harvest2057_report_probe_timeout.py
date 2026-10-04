"""Harvest #2057: BobCallback report probe timeout >=20s."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "jeeves/scripts/Watch-BobWebhooks.ps1"
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest2057_watch_timeout_20():
    text = WATCH.read_text(encoding="utf-8-sig")
    assert "TimeoutSec 20" in text
    assert "TimeoutSec 8" not in text
    assert "2057" in text or "1993" in text


def test_harvest2057_monitor_and_trouble():
    mon = MON.read_text(encoding="utf-8")
    tr = TROUBLE.read_text(encoding="utf-8")
    assert "2057" in mon and "20" in mon
    assert "2057" in tr and "max-time" in tr


def test_harvest2057_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "2057" in text
    assert "20" in text


def test_harvest2057_files_end_with_newline():
    for p in (WATCH, MON, TROUBLE, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
