"""Hostile MRB #2992: FAIL-supersede thin already-covered twin skip (FR #2991)."""
from __future__ import annotations

from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
INTAKE = ROOT / "common" / "scripts" / "intake.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2992_harvest_skill_pins_fr2991_contiguous():
    t = _read(HARVEST)
    assert "FR #2991" in t
    # Bullet still names the thin already-covered FAIL-supersede twin loop (no orphan splice).
    assert "thin already-covered FAIL-supersede twin" in t or (
        "thin already-covered" in t and "FAIL-supersede" in t and "#2991" in t
    )
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_mrb2992_client_and_intake_gates_present():
    ps1 = _read(HARVEST_PS1)
    assert "FR #2991" in ps1
    assert "already cover" in ps1.lower()
    assert "close thin" in ps1.lower() or "thin harvest" in ps1.lower()
    py = _read(INTAKE)
    assert "is_fail_supersede_thin_twin_lesson" in py
    assert "thin_twin_fail_supersede_already_covered" in py
    assert "_THIN_TWIN_CUE_RE" in py


def test_mrb2992_thin_twin_vs_product_msi_gate():
    thin = (
        "MRB FAIL-superseded thin harvest twin; fleet-ops already cover SkipCopy; "
        "close thin twins citing product PRs"
    )
    product = (
        "Earlier MRB FAIL-superseded a twin; MSI RunInstall: when -MsiProductVersion "
        "is set, SkipCopy so heat-laid scripts win"
    )
    assert intake.is_fail_supersede_thin_twin_lesson(thin)
    assert not intake.is_fail_supersede_thin_twin_lesson(product)
