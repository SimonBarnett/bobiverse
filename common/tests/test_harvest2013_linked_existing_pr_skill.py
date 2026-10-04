"""Harvest #2013: intake linked_existing_pr playbook in harvest skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HV = ROOT / "common/.grok/skills/harvest/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest2013_harvest_skill_section():
    text = HV.read_text(encoding="utf-8")
    assert "1812" in text
    assert "linked_existing_pr" in text
    assert "harvest_pr_summary" in text or "draft_pr_error" in text
    assert "\n<<<<<<<" not in text


def test_harvest2013_agent_skills_section():
    text = HAS.read_text(encoding="utf-8")
    assert "1812" in text or "2013" in text
    assert "linked_existing_pr" in text


def test_harvest2013_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "2013" in text or "1812" in text
    assert "linked_existing_pr" in text
    assert "\n<<<<<<<" not in text


def test_harvest2013_files_end_with_newline():
    for p in (HV, HAS, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
