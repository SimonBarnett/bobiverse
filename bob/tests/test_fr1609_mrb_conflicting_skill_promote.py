"""Harvest #1609: CONFLICTING/superseded MRB FAIL playbook in job skills."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"

_TYPO = re.compile(r"(?<![A-Za-z])obiverse-bob-job")
_BB = re.compile(r"bbobiverse-bob-job")


def test_fr1609_mrb_conflicting_section():
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "CONFLICTING" in text
    assert "force-merge" in text.lower() or "force-merge" in text
    assert "DONE FAIL" in text or "DONE MRB" in text
    assert "1609" in text
    assert "fix/rebase" in text or "one fix" in text.lower()
    assert "\n<<<<<<<" not in text and not text.startswith("<<<<<<<")


def test_fr1609_irc_troubleshooting_row():
    text = IRC.read_text(encoding="utf-8")
    assert "CONFLICTING" in text
    assert "force-merge" in text.lower() or "DONE FAIL" in text
    assert _TYPO.search(text) is None
    assert _BB.search(text) is None


def test_fr1609_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1609" in text
    assert "CONFLICTING" in text or "force-merge" in text
    assert "\n<<<<<<<" not in text and not text.startswith("<<<<<<<")
    assert _TYPO.search(text) is None


def test_fr1609_files_end_with_newline():
    for p in (MRB, IRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
