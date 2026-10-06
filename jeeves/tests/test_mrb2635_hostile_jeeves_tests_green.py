"""MRB #2635 hostile gates for FR #2633 (jeeves/tests green on main).

Vision (common/docs/vision.md): fleet MSIs + maintained services; CI must not
reintroduce UTF-8 mojibake or drop the previously-red acceptance pin set.
"""
from __future__ import annotations

from pathlib import Path

import repo_layout

ROOT = Path(repo_layout.ROOT)
WF = ROOT / ".github" / "workflows" / "pytest-gitclaim.yml"
HARVEST = ROOT / "common" / "docs" / "skill-harvest-log.md"


def test_mrb2635_workflow_no_mojibake_and_ascii_arrow():
    text = WF.read_text(encoding="utf-8")
    assert "â" not in text
    assert "Ã" not in text
    line2 = text.splitlines()[1]
    assert "GET /report" in line2 and "later queue_path" in line2
    assert "->" in line2 or "\u2192" in line2


def test_mrb2635_ci_gates_previously_red_pin_set():
    text = WF.read_text(encoding="utf-8")
    assert "Previously-red jeeves acceptance pins (FR #2633)" in text
    for needle in (
        "test_fr1_msi_fleet_acceptance.py",
        "test_mrb2482_pin_set_exact_six",
        "test_fr1518_gated_skill_and_pins_exit0_with_counts",
        "test_harvest1715_nak_busy_workers_map.py",
        "test_clear_orphan_digest_mrb_doing",
    ):
        assert needle in text, needle


def test_mrb2635_harvest_log_restores_2633_and_keeps_2632():
    text = HARVEST.read_text(encoding="utf-8")
    assert "â" not in text
    assert "FR #2633" in text
    assert "#1581" in text and "#1613" in text and "#1715" in text
    assert "FR #2632" in text or "MRB #2634" in text


def test_mrb2635_fomprep_pin_set_includes_eleven():
    """FR #2562 / #2677: reverse #2521 — #11 MRB FAIL verdict is hard-pinned again."""
    import gitclaim

    got = {
        int(ident.lstrip("#"))
        for (repo, ident) in gitclaim._SKIP_FR_ISSUE_PINS
        if repo == "simonbarnett/agentic_fomprep"
    }
    assert got == {3, 7, 8, 9, 11, 20}
    assert 11 in got
