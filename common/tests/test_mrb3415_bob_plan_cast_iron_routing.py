"""MRB #3415: Plan CAST IRON routes harvest to skills-visionary (FR #3318 / #8833).

bobiverse-bob-plan removed; Pack stub + pointer README carry the CAST IRON examples.
"""
from __future__ import annotations

from repo_layout import REPO

PACK = REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
README = REPO / "bob" / "agents" / "plan" / "README.md"


def test_mrb3415_pack_stub_cast_iron_skills_visionary_not_bobiverse_harvest():
    text = PACK.read_text(encoding="utf-8-sig")
    stub_start = text.index("Plan lives in https://github.com/SimonBarnett/skills-visionary")
    stub = text[stub_start : stub_start + 900]
    assert "SimonBarnett/skills-visionary" in stub
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in stub
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in stub
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in stub
    assert README.is_file()
    assert "skills-visionary" in README.read_text(encoding="utf-8")
