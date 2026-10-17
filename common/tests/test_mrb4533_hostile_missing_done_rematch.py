"""MRB #4533 hostile pin: Missing-DONE rematch after sibling self-MRB GIVEUP."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "Missing-DONE rematch: sibling self-MRB GIVEUP leaves tip for another seat; "
    "if ahead_by>0 fold once then PASS leave existing MERGE/SQUASH"
)


def test_mrb4533_hostile_missing_done_rematch_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "Missing-DONE rematch" in text
    assert "sibling self-MRB GIVEUP" in text
    assert "leave existing MERGE/SQUASH" in text
    assert "\u2014" not in NEEDLE and "\u2013" not in NEEDLE