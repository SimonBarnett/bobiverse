"""Harvest #1688: honor require_machine with ACK/GIVEUP lives in job skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1688_job_fr_honor_pin():
    text = FR.read_text(encoding="utf-8")
    assert not FR.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Honor" in text or "honor" in text
    assert "require_machine=" in text
    assert "GIVEUP" in text
    assert "1688" in text
    assert "1687" in text
    assert "ACK then GIVEUP" in text or "ACK then **GIVEUP**" in text


def test_fr1688_job_irc_rule():
    text = IRC.read_text(encoding="utf-8")
    assert "1688" in text
    assert "require_machine=" in text
    assert "GIVEUP" in text
    assert "Machine pin" in text


def test_fr1688_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1688" in text
    assert "require_machine" in text


def test_fr1688_files_end_with_newline():
    for p in (FR, IRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
