"""MRB #5488 hostile pins: FR #4371 harvest skip pins accept FR #4780/#4917 messages."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

TEST = ROOT / "common/tests/test_fr4371_harvest_closed_duplicate_tip_loop.py"
SKILL = ROOT / "common/.grok/skills/harvest/SKILL.md"


def test_mrb5488_pins_accept_all_three_skip_messages():
    t = TEST.read_text(encoding="utf-8")
    for needle in (
        "SKIPPED harvest CLOSED-duplicate lesson loop",
        "SKIPPED harvest lesson-review loop (FR #4780/#4917)",
        "SKIPPED harvest lesson/pin job (FR #4917)",
        "_assert_harvest_skipped",
        "pack client keep.ps1 count",
    ):
        assert needle in t, needle


def test_mrb5488_skill_lesson_review_before_4371_belt():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4780/#4917 lesson-review path first" in text
    assert "FR #4371 / #5481" in text
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")