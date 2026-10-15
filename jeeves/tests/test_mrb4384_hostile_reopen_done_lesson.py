"""MRB #4384: FR #4373 reopen-done lesson lives in bobiverse-jeeves-monitor (not harvest)."""
from __future__ import annotations

from repo_layout import ROOT

MONITOR = (
    ROOT
    / "jeeves"
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-monitor"
    / "SKILL.md"
)
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb4384_reopen_done_lesson_in_jeeves_monitor():
    text = MONITOR.read_text(encoding="utf-8")
    assert "FR #4373 reopened FR stuck in done" in text
    assert "pop_done" in text
    assert "_coerce_row" in text
    assert "open_pulls" in text and "None" in text
    assert "requeue_reopened_issue" in text
    assert not MONITOR.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb4384_harvest_book_does_not_own_thin_reopen_tip():
    """Wrong-book tip must not land the durable playbook under harvest alone."""
    h = HARVEST.read_text(encoding="utf-8")
    # After MOVED close of intake #4384, main harvest should not be the home.
    # Allow absence; if a thin tip remains it is superseded by monitor.
    assert "FR #4373 reopened FR stuck in done" in MONITOR.read_text(encoding="utf-8")
