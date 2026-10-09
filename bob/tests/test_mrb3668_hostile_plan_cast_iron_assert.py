"""docs/mrb-3668: hostile pins for FR #3667 post-Sync plan CAST IRON assert (PR #3668)."""
from __future__ import annotations

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
PLAN_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-plan" / "SKILL.md"
FLEET_SKILL = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
PRODUCT_TEST = ROOT / "bob" / "tests" / "test_fr3667_plan_cast_iron_post_sync_assert.py"


def _read(path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def test_mrb3668_assert_is_soft_warn_only():
    common = _read(COMMON)
    start = common.index("function Assert-BobiversePlanCastIronSkillsVisionary")
    # Stop before Sync-BobiverseAgentFolders body consumes a huge window.
    end = common.index("function Sync-BobiverseAgentFolders", start)
    fn = common[start:end]
    assert "WARN FR #3667" in fn
    assert "INFO FR #3667 plan CAST IRON skills-visionary ok" in fn
    # Soft: never throw / exit 1 from the assert itself.
    assert "throw " not in fn.lower()
    assert "exit 1" not in fn.lower()
    assert "Write-Error" not in fn


def test_mrb3668_assert_called_once_at_end_of_sync_agent_folders():
    common = _read(COMMON)
    start = common.index("function Sync-BobiverseAgentFolders")
    end = common.index("function Install-BobiverseAgentLayer", start)
    sync_fn = common[start:end]
    # Comment + one call; pin the real call site (InstallRoot Destination).
    assert (
        sync_fn.count("Assert-BobiversePlanCastIronSkillsVisionary -InstallRoot")
        == 1
    )
    # Call sits after the foreach refresh loop, before return $made.
    call_i = sync_fn.index(
        "Assert-BobiversePlanCastIronSkillsVisionary -InstallRoot $Destination"
    )
    ret_i = sync_fn.index("return $made", call_i)
    assert call_i < ret_i


def test_mrb3668_heal_skill_rows_contiguous():
    plan = _read(PLAN_SKILL)
    assert "WARN FR #3667" in plan
    assert "Do not re-land #3510 source text" in plan
    fleet = _read(FLEET_SKILL)
    assert "class of #3667" in fleet
    assert "WARN FR #3667" in fleet
    # UTF-8 hygiene on changed skill tips (no mojibake markers).
    assert "â" not in plan
    assert "â" not in fleet


def test_mrb3668_product_fr3667_suite_present():
    assert PRODUCT_TEST.is_file()
    body = _read(PRODUCT_TEST)
    assert "Assert-BobiversePlanCastIronSkillsVisionary" in body
    assert "WARN FR #3667" in body
    assert "INFO FR #3667 plan CAST IRON skills-visionary ok" in body
