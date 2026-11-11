"""Hostile pins for MRB #6616 / FR #6576 build-claim embed gate.

Additive: product PR already wires assert_build_claim_embed into Build-BobEar /
Build-Jeeves. These pins lock fail-closed behaviour (no --allow-missing on the
builder path; throw strings stay contiguous).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_EAR = ROOT / "bob" / "scripts" / "Build-BobEar.ps1"
BUILD_JEEVES = ROOT / "jeeves" / "scripts" / "Build-Jeeves.ps1"
ASSERT_PY = ROOT / "common" / "scripts" / "assert_build_claim_embed.py"


def test_mrb6616_builders_fail_closed_no_allow_missing():
    """Builders must invoke the assert without --allow-missing (exit 2 soft-pass)."""
    for path, label in ((BUILD_EAR, "Build-BobEar"), (BUILD_JEEVES, "Build-Jeeves")):
        text = path.read_text(encoding="utf-8")
        assert "assert_build_claim_embed" in text, label
        # Contiguous fail-closed missing-helper throw (product acceptance).
        assert "assert_build_claim_embed.py missing (fail closed)" in text, label
        assert "assert_build_claim_embed failed (exit" in text, label
        # Never soft-pass the claim embed pin.
        assert "--allow-missing" not in text, label
        assert "assert_build_claim_embed.py missing; skip" not in text, label


def test_mrb6616_assert_invoked_on_work_dir_not_allow_missing_default():
    """CLI default is fail-closed; --allow-missing is opt-in for empty trees only."""
    src = ASSERT_PY.read_text(encoding="utf-8")
    assert "allow-missing" in src
    assert "Exit 2 (not 1) when no PYZ/module is found" in src
    # Structural pins the builders rely on.
    for needle in (
        "_claim_build_route_marker_detail",
        "stale_after_s",
        "stale_claim_s",
        ".reclaim.lock",
        "problems_in_module_code",
    ):
        assert needle in src


def test_mrb6616_builders_pass_work_dir_to_assert():
    """Assert runs against the PyInstaller work dir ($work), where PYZ-00.pyz lives."""
    for path, label in ((BUILD_EAR, "Build-BobEar"), (BUILD_JEEVES, "Build-Jeeves")):
        text = path.read_text(encoding="utf-8")
        # PowerShell: & $Python $assertClaim $work
        assert "$assertClaim $work" in text or "& $Python $assertClaim $work" in text, label
