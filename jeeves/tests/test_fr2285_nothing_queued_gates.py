"""Harvest #2285: nothing queued = focus + require_machine offer gate (extends #2243)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr2285_monitor_nothing_queued_require_machine():
    text = MONITOR.read_text(encoding="utf-8")
    assert "2285" in text
    assert "nothing queued" in text.lower()
    assert "require_machine" in text
    assert "offerable" in text.lower() or "offer set" in text.lower() or "offerable to live" in text.lower()
    assert "2243" in text
    assert not MONITOR.read_bytes().startswith(b"\xef\xbb\xbf")
    assert MONITOR.read_bytes().endswith(b"\n")


def test_fr2285_job_irc_and_harvest_log():
    irc = IRC.read_text(encoding="utf-8")
    log = LOG.read_text(encoding="utf-8")
    assert "2285" in irc and "2285" in log
    assert "require_machine" in irc
    assert "nothing queued" in log.lower()
    assert not LOG.read_bytes().startswith(b"\xef\xbb\xbf")
