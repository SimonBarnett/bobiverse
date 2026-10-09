"""MRB #3703: FR #3686 pack VERSION lesson lives in fleet-ops, not harvest."""
from __future__ import annotations

from repo_layout import ROOT

FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"


def test_mrb3703_fleet_ops_has_fr3686_pack_version_playbook():
    t = FLEET.read_text(encoding="utf-8")
    assert "FR #3686" in t
    assert "Assert-BobiverseStageVersionAligned" in t
    assert "RemoveFile On=install" in t
    assert "never `harvest`" in t or "never park this under `harvest`" in t
    # Contiguous pack-stage window.
    i = t.find("FR #3686")
    assert i >= 0
    window = t[i : i + 350]
    assert "Assert-BobiverseStageVersionAligned" in window or "BUILD.json" in window
    assert "â" not in window


def test_mrb3703_harvest_must_not_own_fr3686_line():
    h = HARVEST.read_text(encoding="utf-8")
    assert "Assert-BobiverseStageVersionAligned" not in h
    assert "packing with -Version N while common\\VERSION lags" not in h


def test_mrb3703_product_pack_still_has_fr3686():
    p = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3686" in p
    assert "Assert-BobiverseStageVersionAligned" in p
