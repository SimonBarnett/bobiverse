"""MRB #4742 hostile pin: docs/mrb skill-only tip may PASS while product PR still open (Refs)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
NEEDLE = (
    "A docs/mrb tip that only pins skill text may PASS while the product PR is still open "
    "when Refs (not Closes) name that PR and the hostile test does not require the product "
    "code on main."
)


def test_harvest_docs_mrb_refs_bullet_contiguous():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "SKILL.md must be UTF-8 without BOM"
    text = SKILL.read_text(encoding="utf-8")
    assert NEEDLE in text, "harvest playbook bullet must stay contiguous"


def test_needle_is_single_harvested_bullet():
    text = SKILL.read_text(encoding="utf-8")
    assert text.count("docs/mrb tip that only pins skill text may PASS") == 1
