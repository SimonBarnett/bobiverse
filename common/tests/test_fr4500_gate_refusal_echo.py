"""FR #4500: a quoted gate refusal is not a new owner hold."""

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
    "This seat must not merge it.\n"
)
PASS_BOARD = "## MRB board\n\n**Verdict:** PASS\n"
ECHO = (
    "MRB PASS - held, not merged (hold: ## MRB hand-back (GIVEUP), "
    "phrase must not merge). mrb_merge_gate.py exit 2. Auto-merge disabled.\n"
)
REAL_HOLD = "On hold: must not merge until the parent tip lands."


def _owner(body: str, created: str) -> dict:
    return {
        "user": {"login": "SimonBarnett"},
        "author_association": "OWNER",
        "body": body,
        "created_at": created,
    }


def test_fr4500_gate_echo_after_hand_back_is_not_a_hold():
    comments = [
        _owner(HANDBACK, "2026-10-15T09:59:16Z"),
        _owner(PASS_BOARD, "2026-10-16T21:36:51Z"),
        _owner(ECHO, "2026-10-16T21:37:40Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr4500_real_hold_after_echo_still_refuses():
    comments = [
        _owner(ECHO, "2026-10-16T21:37:40Z"),
        _owner(REAL_HOLD, "2026-10-16T21:40:00Z"),
        _owner(PASS_BOARD, "2026-10-16T21:41:00Z"),
    ]
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "hold" in reason.lower()


def test_fr4500_echo_does_not_clear_earlier_real_hold():
    comments = [
        _owner(REAL_HOLD, "2026-10-16T21:00:00Z"),
        _owner(ECHO, "2026-10-16T21:37:40Z"),
        _owner(PASS_BOARD, "2026-10-16T21:41:00Z"),
    ]
    ok, _reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False


def test_fr4500_plain_must_not_merge_is_still_a_hold():
    comments = [
        _owner("must not merge", "2026-10-16T21:37:40Z"),
        _owner(PASS_BOARD, "2026-10-16T21:41:00Z"),
    ]
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "must not merge" in reason.lower()
