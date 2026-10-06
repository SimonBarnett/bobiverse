"""MRB #2963 FAIL fix: MSI Copy-BobiverseVersion playbook lives in fleet-ops, not harvest.

Product gate on main via PR #2950 (FR #2948). Harvest tip #2951 + docs/mrb #2963 wrongly
parked/pinned the lesson under harvest/SKILL.md; this module pins the correct home.
"""
from __future__ import annotations

from pathlib import Path

HARVEST = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
FLEET = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
COMMON = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"

NEEDLE = (
    "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion "
    "and must not clobber InstallRoot\\VERSION with stale common\\VERSION "
    "when RepoRoot==InstallRoot"
)


def test_mrb2963_harvest_does_not_hold_msi_copy_version_lesson():
    text = HARVEST.read_text(encoding="utf-8")
    assert NEEDLE not in text
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_mrb2963_fleet_ops_holds_fr2948_playbook():
    text = FLEET.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2948" in text
    assert "MsiProductVersion" in text or "-MsiProductVersion" in text
    assert "Copy-BobiverseVersion" in text
    assert "RepoRoot==InstallRoot" in text or "RepoRoot" in text


def test_mrb2963_product_copy_bobiverse_version_honours_msi_product_version():
    """Product gate already on main via PR #2950."""
    ps1 = COMMON.read_text(encoding="utf-8")
    assert "function Copy-BobiverseVersion" in ps1
    assert "MsiProductVersion" in ps1
    assert "FR #2948" in ps1
    assert "RepoRoot" in ps1 and "InstallRoot" in ps1
