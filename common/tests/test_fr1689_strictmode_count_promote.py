"""Harvest #1689: StrictMode @() before .Count lives in skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
PATHS = (FLEET, FR, MRB, LOG, Path(__file__))


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_fr1689_fleet_ops_strictmode():
    text = _utf8_no_bom(FLEET)
    assert "StrictMode" in text
    assert "@()" in text or "@(" in text
    assert "1664" in text or "1689" in text


def test_fr1689_job_fr_worktree_note():
    text = _utf8_no_bom(FR)
    assert "StrictMode" in text or "1664" in text
    assert ".Count" in text or "@()" in text
    assert "1689" in text


def test_fr1689_job_mrb_sibling_conflict():
    text = _utf8_no_bom(MRB)
    assert "@()" in text or "StrictMode" in text
    assert "1694" in text or "soft-cap" in text


def test_fr1689_skill_harvest_log():
    text = _utf8_no_bom(LOG)
    assert "1689" in text
    assert "StrictMode" in text


def test_fr1689_files_end_with_newline():
    for p in PATHS:
        assert p.read_bytes().endswith(b"\n"), p
