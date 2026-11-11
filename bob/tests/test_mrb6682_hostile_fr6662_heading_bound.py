"""docs/mrb-6682: hostile pins for FR #6662 / PR #6682.

Pins heading-bounded ``## Harvest-lesson intake PRs`` slice so Short triage
``Generalised?`` stays contiguous after section growth past a fixed 2200 window.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

JOB_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
PIN = ROOT / "bob" / "tests" / "test_fr3317_harvest_light_triage.py"


def test_mrb6682_fixed_2200_misses_generalised_heading_bound_keeps_it():
    text = JOB_MRB.read_text(encoding="utf-8-sig")
    ss = text.index("## Harvest-lesson intake PRs")
    se = text.find("\n## ", ss + 4)
    assert se > ss
    section = text[ss:se]
    assert "Short triage checklist (FR #3317)" in section
    assert "Generalised?" in section
    # Regression: checklist now sits ~2132 into the section; fixed 2200 clips it.
    assert "Generalised?" not in text[ss : ss + 2200]
    assert "Skill / markdown diff hygiene" in text[se : se + 80]


def test_mrb6682_product_pin_uses_heading_bound_not_fixed_2200():
    t = PIN.read_text(encoding="utf-8-sig")
    assert 'text.find("\\n## "' in t or "text.find('\\n## '" in t
    assert "section_start + 2200" not in t
    assert "FR #6662" in t
