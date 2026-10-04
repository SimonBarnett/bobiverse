"""Harvest #2001: living FR re-file when intake is harvest-only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_fr2001_harvest_living_fr_section():
    text = _utf8_no_bom(HARVEST)
    assert "2001" in text
    assert "feature-request" in text
    assert "living FR" in text or "Canonical living" in text or "living product FR" in text.lower()
    assert "1993" in text


def test_fr2001_harvest_agent_skills_bullet():
    text = _utf8_no_bom(HAS)
    assert "2001" in text
    assert "feature-request" in text
    assert "living FR" in text.lower() or "Living product FR" in text


def test_fr2001_skill_harvest_log():
    text = _utf8_no_bom(LOG)
    assert "2001" in text
    assert "feature-request" in text
