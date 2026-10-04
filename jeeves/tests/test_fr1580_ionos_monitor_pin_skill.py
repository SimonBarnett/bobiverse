"""Harvest #1580: ionos pin for monitor StartPending/idle+ungated lives in skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
JOB = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1580_monitor_skill_ionos_pin():
    raw = MON.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "StartPending" in text
    assert "ungated" in text.lower()
    assert "require_machine" in text
    assert "1550" in text or "1574" in text
    assert "title" in text.lower()  # cue words in intake titles


def test_fr1580_job_fr_cues():
    raw = JOB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "StartPending" in text
    assert "ungated" in text.lower()
    assert "1550" in text
    assert "GIVEUP" in text
    assert "marchhare" in text.lower() or "Non-matching" in text


def test_fr1580_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1580" in text
    assert "StartPending" in text or "ungated" in text.lower()
    assert "<<<<<<" not in text


def test_fr1580_files_end_with_newline():
    for p in (MON, JOB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
