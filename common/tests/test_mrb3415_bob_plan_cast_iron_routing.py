"""MRB #3415: bobiverse-bob-plan CAST IRON routes Plan harvest to skills-visionary (FR #3318)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-plan" / "SKILL.md"


def test_mrb3415_bob_plan_cast_iron_skills_visionary_not_bobiverse_harvest():
    text = SKILL.read_text(encoding="utf-8-sig")
    head = "\n".join(text.splitlines()[:25])
    assert "FR #3318" in head
    assert "SimonBarnett/skills-visionary" in head
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in head
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in head
    # CAST IRON example must not default Plan lessons to bobiverse harvest.
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in head
