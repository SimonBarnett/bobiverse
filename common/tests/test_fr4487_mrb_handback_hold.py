"""FR #4487: a self-MRB hand-back is not a permanent owner hold."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")

HANDBACK = (
    "## MRB hand-back (GIVEUP)\n\n"
    "Tip is a harvest-lesson opened by this seat. "
    "**self-MRB**; this seat must not merge it.\n"
)
PASS_BOARD = "## MRB board\n\n**Verdict:** PASS\n"
REAL_HOLD = "On hold: must not merge until the parent tip lands."


def _owner(body: str, created: str) -> dict:
    return {
        "user": {"login": "SimonBarnett"},
        "author_association": "OWNER",
        "body": body,
        "created_at": created,
    }


def test_fr4487_hand_back_must_not_merge_is_not_owner_hold():
    comments = [
        _owner(HANDBACK, "2026-10-15T09:59:16Z"),
        _owner(PASS_BOARD, "2026-10-16T21:36:51Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr4487_real_hold_after_hand_back_still_refuses():
    comments = [
        _owner(HANDBACK, "2026-10-15T09:59:16Z"),
        _owner(REAL_HOLD, "2026-10-16T10:00:00Z"),
        _owner(PASS_BOARD, "2026-10-16T21:36:51Z"),
    ]
    hold = mrb_merge_gate.find_active_owner_hold(comments)
    assert hold is not None
    assert "on hold" in hold.lower()
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "hold" in reason.lower()


def test_fr4487_hand_back_does_not_clear_earlier_real_hold():
    comments = [
        _owner(REAL_HOLD, "2026-10-15T09:00:00Z"),
        _owner(HANDBACK, "2026-10-15T09:59:16Z"),
        _owner(PASS_BOARD, "2026-10-16T21:36:51Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None
    ok, _reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False


def test_fr4487_skill_documents_hand_back_skip():
    skill = (
        ROOT
        / "bob"
        / ".grok"
        / "skills"
        / "bobiverse-bob-job-mrb"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "FR #4487" in text
    assert "## MRB hand-back" in text
