"""Harvest #1674: never Closes skill harvest from unrelated PRs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
PATHS = (FR, MRB, HAS, LOG, Path(__file__))


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_fr1674_job_fr_rule():
    text = _utf8_no_bom(FR)
    assert "label:skill" in text
    assert "1674" in text
    assert "Refs" in text
    assert "unrelated" in text.lower()


def test_fr1674_job_mrb_bullet():
    text = _utf8_no_bom(MRB)
    assert "1674" in text
    assert "Closes" in text and "skill" in text.lower()


def test_fr1674_harvest_agent_skills():
    text = _utf8_no_bom(HAS)
    assert "1674" in text
    assert "Closes" in text


def test_fr1674_skill_harvest_log():
    text = _utf8_no_bom(LOG)
    assert "1674" in text
    assert "Never Closes skill harvest" in text


def test_fr1674_files_end_with_newline():
    for p in PATHS:
        assert p.read_bytes().endswith(b"\n"), p
