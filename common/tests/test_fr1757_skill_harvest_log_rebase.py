"""FR #1757: skill-harvest-log parallel promote rebase / keep-both playbook."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    assert "\n<<<<<<<" not in text and not text.startswith("<<<<<<<")
    return text


def test_fr1757_harvest_agent_skills_keep_both():
    text = _utf8_no_bom(HARVEST)
    assert "skill-harvest-log parallel promotes" in text
    assert "keep both dated sections" in text
    assert "1757" in text
    assert "1750" in text


def test_fr1757_job_mrb_harvest_log_race():
    text = _utf8_no_bom(MRB)
    assert "skill-harvest-log.md" in text
    assert "keep both dated sections" in text
    assert "1757" in text


def test_fr1757_skill_harvest_log_entry():
    text = _utf8_no_bom(LOG)
    assert "1757" in text
    assert "keep both dated sections" in text
    assert "1750" in text
