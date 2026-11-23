"""docs/mrb-3510: hostile pins for FR #3506 Plan CAST IRON (FR #8833 retarget).

In-tree Plan AGENTS removed; pointer README + Pack stub carry skills-visionary CAST IRON.
"""
from __future__ import annotations

from repo_layout import ROOT

README = ROOT / "bob/agents/plan/README.md"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"


def test_mrb3510_readme_and_pack_skills_visionary():
    t = README.read_text(encoding="utf-8")
    assert "skills-visionary" in t
    assert "FR #8833" in t or "8833" in t
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3506" in pack or "skills-visionary" in pack
    assert "Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary" in pack
    assert "\u2192" not in pack or "â" not in pack  # UTF-8 hygiene on stub


def test_mrb3510_fr3506_product_tests_present():
    path = ROOT / "bob/tests/test_fr3506_plan_cast_iron_skills_visionary.py"
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "skills-visionary" in body
    assert "CAST IRON" in body
