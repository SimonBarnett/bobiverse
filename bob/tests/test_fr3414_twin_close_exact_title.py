"""FR #3414: MRB twin-close filters must use exact title needles, not broad regex."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILL = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"


def test_fr3414_cast_iron_twin_close_filter_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    # FR #3803 extends the header to (FR #3414 / FR #3803); keep FR #3414 contiguous.
    assert "**CAST IRON twin-close filter (FR #3414" in text
    assert "FR #3414" in text
    assert "exact lesson title / tip title needle" in text
    assert "Phase-2|normalize|stack" in text
    assert "that tip's own durable product/skill PR" in text
    assert "MRB #3366" in text


def test_fr3414_checklist_item_4_exact_needle():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3414" in text
    assert "exact lesson/title needle" in text
    assert "not the assigned MRB URL unless exact twin" in text
