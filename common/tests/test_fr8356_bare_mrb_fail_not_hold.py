"""FR #8356: a bare MRB FAIL @ <sha> comment is a seat verdict, not an owner hold."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")

# Shape from SimonBarnett/toray#28 (no ## MRB board / **Verdict:** markers).
BARE_FAIL = "MRB FAIL @ b8c5721 Do not merge"
PASS_BOARD = "## MRB board\n\n**Verdict:** PASS\n"
REAL_HOLD = "On hold: must not merge until the parent tip lands."


def _owner(body: str, created: str) -> dict:
    return {
        "user": {"login": "SimonBarnett"},
        "author_association": "OWNER",
        "body": body,
        "created_at": created,
    }


def test_fr8356_bare_mrb_fail_is_not_owner_hold():
    comments = [
        _owner(BARE_FAIL, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate._is_mrb_board_comment(BARE_FAIL) is True
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr8356_real_hold_after_bare_fail_still_refuses():
    comments = [
        _owner(BARE_FAIL, "2026-11-18T10:00:00Z"),
        _owner(REAL_HOLD, "2026-11-18T10:30:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    hold = mrb_merge_gate.find_active_owner_hold(comments)
    assert hold is not None
    assert "on hold" in hold.lower()
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "hold" in reason.lower()


def test_fr8356_bare_fail_does_not_clear_earlier_real_hold():
    comments = [
        _owner(REAL_HOLD, "2026-11-18T09:00:00Z"),
        _owner(BARE_FAIL, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None
    ok, _reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is False


def test_fr8356_do_not_merge_without_fail_sha_still_holds():
    body = "Do not merge this pull request."
    comments = [
        _owner(body, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate._is_mrb_board_comment(body) is False
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None


def test_fr8441_backtick_sha_is_not_owner_hold():
    body = "MRB FAIL @ `deadbeef` Do not merge"
    comments = [
        _owner(body, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate._is_mrb_board_comment(body) is True
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr8441_quoted_sha_is_not_owner_hold():
    body = "MRB FAIL @ 'deadbeef' Do not merge"
    assert mrb_merge_gate._is_mrb_board_comment(body) is True


def test_fr8441_mid_line_backtick_still_holds():
    body = "Please MRB FAIL @ `deadbeef` Do not merge"
    comments = [
        _owner(body, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate._is_mrb_board_comment(body) is False
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None


def test_fr8356_mrb_fail_without_sha_still_holds():
    body = "MRB FAIL. Do not merge."
    comments = [
        _owner(body, "2026-11-18T10:00:00Z"),
        _owner(PASS_BOARD, "2026-11-18T11:00:00Z"),
    ]
    assert mrb_merge_gate._is_mrb_board_comment(body) is False
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None
