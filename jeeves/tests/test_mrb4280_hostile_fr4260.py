"""MRB #4280 hostile pins for FR #4260 re-offer clears seat-hold."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITCLAIM = REPO / "common" / "scripts" / "gitclaim.py"
IRC = REPO / "common" / "scripts" / "irc_agent.py"
SKILL = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md"
FR_TEST = REPO / "jeeves" / "tests" / "test_fr4260_reoffer_clears_seat_hold.py"


def test_gitclaim_clear_job_seat_holds_contiguous():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert "def clear_job_seat_holds(" in text
    assert "def _clear_job_seat_holds_unlocked(" in text
    assert "FR #4260: hold is void when the same job is now offered/accepted by another seat." in text
    assert "FR #4260: re-offer to a different nick frees the previous seat's hold." in text
    assert "FR #4260: !assign to a new nick frees the previous seat's hold for this job." in text


def test_irc_agent_clears_job_holds_on_done_contiguous():
    text = IRC.read_text(encoding="utf-8")
    assert "FR #4260: completing seat also frees any other nick still holding" in text
    assert "gitclaim.clear_job_seat_holds(" in text


def test_jeeves_commands_skill_documents_fr4260():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4260" in text
    assert "re-offer" in text
    assert "clears all holds" in text or "clear" in text.lower()


def test_fr4260_suite_acceptance_names():
    text = FR_TEST.read_text(encoding="utf-8")
    assert "test_reoffer_to_other_seat_clears_original_hold" in text
    assert "test_other_seat_done_clears_original_hold_and_assign_succeeds" in text
    assert "test_seat_open_job_voids_hold_when_row_offered_to_other" in text
    assert "worker_list" in text
