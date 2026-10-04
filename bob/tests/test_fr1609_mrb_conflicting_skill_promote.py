"""Harvest #1609: CONFLICTING/superseded MRB FAIL playbook in job skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1609_mrb_conflicting_section():
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "CONFLICTING" in text
    assert "force-merge" in text.lower() or "force-merge" in text
    assert "DONE FAIL" in text or "DONE MRB" in text
    assert "1609" in text
    assert "not an automatic FAIL" in text


def test_fr1609_irc_troubleshooting_row():
    text = IRC.read_text(encoding="utf-8")
    assert "CONFLICTING" in text
    assert "force-merge" in text.lower() or "DONE FAIL" in text


def test_fr1609_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1609" in text
    assert "CONFLICTING" in text or "force-merge" in text
    assert "<<<<<<< HEAD" not in text


def test_fr1609_files_end_with_newline():
    for p in (MRB, IRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
