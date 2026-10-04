"""Harvest #1657: conflict-marker CAST IRON before merge lives in job skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1657_mrb_conflict_marker_cast_iron():
    text = MRB.read_text(encoding="utf-8")
    assert "check_conflict_markers" in text
    assert "1634" in text
    assert "refuse merge" in text.lower() or "Never merge conflict markers" in text
    assert "behind" in text.lower()


def test_fr1657_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1657" in text or "1634" in text
    assert "conflict" in text.lower()
    assert "<<<<<<" not in text


def test_fr1657_files_end_with_newline():
    for p in (MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
