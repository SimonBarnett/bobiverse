"""FR #3506 / #8833: Plan CAST IRON lives in skills-visionary; bobiverse keeps a pointer.

FR #8833 removed bob/agents/plan AGENTS + bobiverse-bob-plan. Pack writes a stub
plan\\AGENTS.md with skills-visionary CAST IRON examples (see Pack-BobiverseRelease).
"""
from __future__ import annotations

from repo_layout import ROOT

README = ROOT / "bob/agents/plan/README.md"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"


def test_fr3506_pointer_readme_routes_to_skills_visionary():
    t = README.read_text(encoding="utf-8")
    assert "SimonBarnett/skills-visionary" in t
    assert "PlanAgent.exe" in t or "releases/latest" in t


def test_fr3506_pack_stub_agents_cast_iron_skills_visionary():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in text
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary" in text
    # Stub must not teach bobiverse as the Plan CAST IRON example.
    stub_start = text.index("Plan lives in https://github.com/SimonBarnett/skills-visionary")
    stub = text[stub_start : stub_start + 800]
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse" not in stub
