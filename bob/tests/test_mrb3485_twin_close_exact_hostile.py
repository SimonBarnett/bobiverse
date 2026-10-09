"""docs/mrb-3485: hostile pins for FR #3414 exact-title twin-close CAST IRON."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
PRODUCT = ROOT / "bob/tests/test_fr3414_twin_close_exact_title.py"


def test_mrb3485_cast_iron_forbids_broad_regex_and_wrong_cite():
    t = SKILL.read_text(encoding="utf-8")
    # FR #3803 extends header; FR #3414 phrase must remain contiguous.
    assert "**CAST IRON twin-close filter (FR #3414" in t
    assert "Never use a broad" in t
    assert "Phase-2|normalize|stack" in t
    assert "that tip's own durable product/skill PR" in t
    assert "exact twin" in t
    assert "MRB #3366" in t


def test_mrb3485_checklist_item_4_and_product_tests():
    t = SKILL.read_text(encoding="utf-8")
    assert "FR #3414" in t
    assert "exact lesson/title needle" in t
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3414_cast_iron_twin_close_filter_contiguous" in p
    assert "test_fr3414_checklist_item_4_exact_needle" in p
