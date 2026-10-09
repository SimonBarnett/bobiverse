"""docs/mrb-3690: hostile pins for FR-3686 pack VERSION alignment (PR #3690)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
PRODUCT = ROOT / "airc/tests/test_fr3686_pack_version_aligned.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb3690_pack_stamps_and_asserts_version():
    t = _read(PACK)
    assert "FR #3686" in t
    assert "WriteAllText((Join-Path $stage 'VERSION')" in t
    assert "Assert-BobiverseStageVersionAligned" in t
    assert "RmStaleVersion" in t
    assert "SetAttribute('On', 'install')" in t
    assert "RemoveFile" in t


def test_mrb3690_common_assert_helper():
    t = _read(COMMON)
    assert "function Assert-BobiverseStageVersionAligned" in t
    assert "FR #3686" in t
    assert "BUILD.json" in t


def test_mrb3690_product_pin_exists():
    t = _read(PRODUCT)
    assert "0.1.99" in t
    assert "SkipMsi" in t
    assert "Assert-BobiverseStageVersionAligned" in t or "stage version aligned" in t.lower() or "FR #3686" in t