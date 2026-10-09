"""docs/mrb-3726: hostile pin FR #3717 Clear cdk.out* cmd rmdir before worktree remove."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
PRODUCT = REPO / "jeeves" / "tests" / "test_fr3717_clear_cdkout_rmdir.py"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"


def test_mrb3726_clear_helpers_and_call_order():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "function Remove-BobiverseDeepWorktreeDirs" in t
    assert "function Remove-BobiversePathForce" in t
    assert "FR #3717 pre-rmdir deep tree" in t
    assert "FR #3717 leftover rmdir" in t
    assert "cdk.out*" in t or "cdk.out" in t
    assert "rmdir /s /q" in t
    # Pre-rmdir before git worktree remove; leftover force after.
    i_deep = t.find("Remove-BobiverseDeepWorktreeDirs -WorktreePath")
    i_git = t.find("git worktree remove")
    i_force = t.find("Remove-BobiversePathForce -Path")
    assert i_deep > 0 and i_git > 0 and i_force > 0
    assert i_deep < i_git < i_force
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)


def test_mrb3726_product_pin_and_skills():
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3717_clear_script_pins_cdkout_rmdir" in p
    assert "test_fr3717_pre_rmdir_removes_cdkout_before_git" in p
    fr = FR_SKILL.read_text(encoding="utf-8")
    fleet = FLEET.read_text(encoding="utf-8")
    assert "3717" in fr and "cdk.out" in fr
    assert "3717" in fleet and "Filename too long" in fleet
