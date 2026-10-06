"""Hostile MRB #2951: harvest SKILL keeps MSI Copy-BobiverseVersion / MsiProductVersion lesson (FR #2948)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
COMMON = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"


def test_mrb2951_harvest_skill_msi_copy_version_lesson_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in text
    # Contiguous playbook from lesson(harvest) PR #2951 / FR #2948
    needle = (
        "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion "
        "and must not clobber InstallRoot\\VERSION with stale common\\VERSION "
        "when RepoRoot==InstallRoot"
    )
    assert needle in text
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_mrb2951_product_copy_bobiverse_version_honours_msi_product_version():
    """Product gate already on main via PR #2950; hostile pin that skill lesson still matches code."""
    ps1 = COMMON.read_text(encoding="utf-8")
    assert "function Copy-BobiverseVersion" in ps1
    assert "MsiProductVersion" in ps1
    assert "FR #2948" in ps1
    assert "RepoRoot" in ps1 and "InstallRoot" in ps1
