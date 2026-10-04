"""Harvest #1981: fix-PR race after DONE PASS -> land PR playbook."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest1981_mrb_fix_pr_race_section():
    text = MRB.read_text(encoding="utf-8")
    assert not MRB.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Fix-PR race after DONE" in text
    assert "1981" in text
    assert "land PR" in text.lower() or "land PR" in text
    assert "known-good tip" in text
    assert "origin/main" in text
    assert "\n<<<<<<<" not in text


def test_harvest1981_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1981" in text
    assert "land PR" in text.lower() or "known-good" in text
    assert "\n<<<<<<<" not in text


def test_harvest1981_files_end_with_newline():
    for p in (MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
