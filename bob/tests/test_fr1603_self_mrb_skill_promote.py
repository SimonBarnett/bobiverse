"""Harvest #1603: self-MRB GIVEUP wire lives in job skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1603_mrb_self_mrb_section():
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Self-MRB" in text
    assert "GIVEUP" in text
    assert "self-MRB" in text
    assert "1603" in text or "1578" in text


def test_fr1603_irc_mentions_giveup():
    text = IRC.read_text(encoding="utf-8")
    assert "self-MRB" in text or "Self-MRB" in text
    assert "GIVEUP" in text


def test_fr1603_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1603" in text
    assert "self-MRB" in text or "Self-MRB" in text
    assert "<<<<<<" not in text


def test_fr1603_files_end_with_newline():
    for p in (MRB, IRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
