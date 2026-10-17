"""MRB #4558 hostile pin: FR re-offer in_ready suffix playbook."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "FR re-offer in_ready suffix after FR-3344: DONE with covering PR after pin verify; "
    "never second implement PR"
)


def test_mrb4558_hostile_in_ready_reoffer_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    assert "rate_remaining" in text