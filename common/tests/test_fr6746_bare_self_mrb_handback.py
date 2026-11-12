"""FR #6746: bare self-MRB hand-back (no ## MRB hand-back header) is not an owner hold."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")

# Exact shape seen on agentic_fomprep#474 (flamingo seat via gh as OWNER).
BARE_HANDBACK = (
    "self-MRB: flamingo-17568 opened this docs/mrb-468 pin. "
    "Hand back for a different seat. Do not merge from this seat."
)
PASS_BOARD = "## MRB board\n\n**Verdict:** PASS\n"
REAL_HOLD = "On hold: must not merge until the parent tip lands."
HEADER_HANDBACK = (
    "## MRB hand-back (GIVEUP)\n\n"
    "Tip is a harvest-lesson opened by this seat. "
    "**self-MRB**; this seat must not merge it.\n"
)


def _owner(body: str, created: str) -> dict:
    return {
        "user": {"login": "SimonBarnett"},
        "author_association": "OWNER",
        "body": body,
        "created_at": created,
    }


def test_fr6746_bare_self_mrb_handback_is_not_owner_hold():
    comments = [
        _owner(BARE_HANDBACK, "2026-11-12T11:48:31Z"),
        _owner(PASS_BOARD, "2026-11-12T12:00:00Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr6746_is_mrb_board_comment_recognises_bare_handback():
    assert mrb_merge_gate._is_mrb_board_comment(BARE_HANDBACK) is True
    assert mrb_merge_gate._is_mrb_board_comment(HEADER_HANDBACK) is True
    assert mrb_merge_gate._is_mrb_board_comment(REAL_HOLD) is False


def test_fr6746_real_hold_after_bare_handback_still_refuses():
    comments = [
        _owner(BARE_HANDBACK, "2026-11-12T11:48:31Z"),
        _owner(REAL_HOLD, "2026-11-12T11:50:00Z"),
        _owner(PASS_BOARD, "2026-11-12T12:00:00Z"),
    ]
    hold = mrb_merge_gate.find_active_owner_hold(comments)
    assert hold is not None
    assert "on hold" in hold.lower()
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "hold" in reason.lower()


def test_fr6746_bare_handback_does_not_clear_earlier_real_hold():
    comments = [
        _owner(REAL_HOLD, "2026-11-12T11:00:00Z"),
        _owner(BARE_HANDBACK, "2026-11-12T11:48:31Z"),
        _owner(PASS_BOARD, "2026-11-12T12:00:00Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None
    ok, _reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False


def test_fr6746_self_mrb_alone_without_hand_back_phrase_still_can_hold():
    """A comment that only says self-MRB + do not merge without the hand-back
    phrase is still an owner hold (narrow skip)."""
    body = "self-MRB: this seat authored the tip. Do not merge."
    comments = [
        _owner(body, "2026-11-12T11:48:31Z"),
        _owner(PASS_BOARD, "2026-11-12T12:00:00Z"),
    ]
    # Without "Hand back for a different seat", HOLD_TEXT_RE still matches.
    assert mrb_merge_gate._is_mrb_board_comment(body) is False
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None
