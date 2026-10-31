"""MRB #5493 hostile pins: ExistingPrUrl harvest skip before lesson-review (FR #5483/#4288)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SCRIPT = ROOT / "common/scripts/Invoke-BobiverseHarvest.ps1"


def test_mrb5493_existing_pr_skip_before_lesson_review_stdout():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    i4288 = text.find("SKIPPED harvest ExistingPrUrl tip-loop")
    i4780 = text.find("SKIPPED harvest lesson-review loop")
    assert i4288 >= 0 and i4780 >= 0
    assert i4288 < i4780
    assert "FR #5483" in text


def test_mrb5493_mrb4291_asserts_lesson_review_absent():
    t = (ROOT / "common/tests/test_mrb4291_hostile_fr4288.py").read_text(encoding="utf-8")
    assert 'assert "SKIPPED harvest lesson-review loop" not in r.stdout' in t
    assert "test_fr5483_existing_pr_skip_before_lesson_review" in t