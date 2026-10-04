"""Harvest #1674: never Closes skill harvest from unrelated PRs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1674_job_fr_rule():
    text = FR.read_text(encoding="utf-8")
    assert "label:skill" in text
    assert "1674" in text
    assert "Refs" in text


def test_fr1674_job_mrb_bullet():
    text = MRB.read_text(encoding="utf-8")
    assert "1674" in text
    assert "Closes" in text and "skill" in text.lower()


def test_fr1674_harvest_agent_skills():
    text = HAS.read_text(encoding="utf-8")
    assert "1674" in text
    assert "Closes" in text


def test_fr1674_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1674" in text
    assert "<<<<<<" not in text


def test_fr1674_files_end_with_newline():
    for p in (FR, MRB, HAS, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
