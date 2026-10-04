"""Harvest #1689: StrictMode @() before .Count lives in skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1689_fleet_ops_strictmode():
    text = FLEET.read_text(encoding="utf-8")
    assert "StrictMode" in text
    assert "@()" in text or "@(" in text
    assert "1664" in text or "1689" in text


def test_fr1689_job_fr_worktree_note():
    text = FR.read_text(encoding="utf-8")
    assert "StrictMode" in text or "1664" in text
    assert ".Count" in text or "@()" in text


def test_fr1689_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1689" in text
    assert "<<<<<<" not in text


def test_fr1689_files_end_with_newline():
    for p in (FLEET, FR, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
