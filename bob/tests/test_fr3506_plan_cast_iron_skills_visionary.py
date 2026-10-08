"""FR #3506: Plan CAST IRON examples must use -Repo SimonBarnett/skills-visionary.

Install trees stuck on old revs (e.g. 0.1.25 / 10826db) still showed bobiverse
examples; tracked sources on main already route Plan process harvest to
skills-visionary (FR #3318 / PR #3415 / docs #3424 / how-to-plan-only #3433).
CLAUDE.md / GROK.md are composed from AGENTS.md at Pack/Sync — pin the source.
"""
from __future__ import annotations

from repo_layout import ROOT

AGENTS = ROOT / "bob/agents/plan/AGENTS.md"
VISIONARY = ROOT / "bob/agents/plan/.grok/skills/visionary/SKILL.md"
HSV = ROOT / "bob/agents/plan/.grok/skills/harvest-skills-visionary/SKILL.md"
BOB_PLAN = ROOT / "bob/.grok/skills/bobiverse-bob-plan/SKILL.md"


def _cast_iron_block(text: str) -> str:
    """First CAST IRON harvest block (through rule 4 / end of blockquote)."""
    assert "CAST IRON RULE - HARVEST" in text
    start = text.index("CAST IRON RULE - HARVEST")
    # Take a generous window covering Report + Harvest examples.
    return text[start : start + 2500]


def test_fr3506_plan_agents_cast_iron_skills_visionary():
    t = AGENTS.read_text(encoding="utf-8")
    block = _cast_iron_block(t)
    assert "-Repo SimonBarnett/skills-visionary" in block
    assert (
        "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in block
    )
    assert (
        "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in block
    )
    # Must not show bobiverse as the CAST IRON example command.
    assert (
        "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in block
    )
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/bobiverse" not in block
    # Explicit forbid remains.
    assert "Never** park Plan lessons under `-Repo SimonBarnett/bobiverse`" in block or (
        "Never park Plan lessons under `-Repo SimonBarnett/bobiverse`" in block
        or "Never** park Plan lessons under `-Repo SimonBarnett/bobiverse` harvest" in block
    )


def test_fr3506_visionary_and_hsv_cast_iron_skills_visionary():
    for path in (VISIONARY, HSV):
        t = path.read_text(encoding="utf-8")
        block = _cast_iron_block(t)
        assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in block
        assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in block
        assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in block


def test_fr3506_bobiverse_bob_plan_cast_iron_and_fleet_carveout():
    t = BOB_PLAN.read_text(encoding="utf-8")
    block = _cast_iron_block(t)
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in block
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in block
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in block
    # Fleet-tooling carve-out may mention bobiverse only as the exception.
    assert "skills-visionary" in block
    assert (
        "bobiverse` only for bob-worker" in block
        or "only for bob-worker/tray/fleet" in block
        or "bob-worker/tray/fleet tooling" in block
    )
