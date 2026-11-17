"""FR #8107: mrb_merge_gate must see Verdict PASS on full (>400 char) boards."""
from __future__ import annotations

import mrb_merge_gate as gate


def _fat_pass_board(*, with_verdict: bool = True, with_pass_at: bool = False) -> str:
    """Build a realistic full board whose Verdict sits well past 400 chars."""
    filler = (
        "### Vision\n"
        "Judged against bob/VISION.md S2 One-window worker and S4 shop wire. "
        "A paid OpenCode seat that dies mid-job with bare turn_ended exit fails "
        "the objective for fleet Windows boxes running ircBob plus TipForm.\n\n"
        "### Tests\n"
        "Local pytest bob/tests/test_fr8091_opencode_epipe.py and related "
        "test_fr8018 / test_fr8069 / test_fr7671 modules - thirty two passed. "
        "check_conflict_markers.py OK on the tip worktree before the board.\n\n"
        "### Docs\n"
        "No separate docs/mrb pin - tip tests already cover acceptance criteria "
        "for drain until EOF, rich GIVEUP with exit code and stderr tail, and "
        "one worktree-safe EPIPE retry in the OpenCode launch wrapper.\n\n"
    )
    # Ensure the filler alone is already > 400 characters before Verdict.
    assert len(filler) > 400, len(filler)
    parts = ["## MRB board\n\n", filler]
    if with_verdict:
        parts.append("**Verdict:** PASS\n")
    if with_pass_at:
        parts.append("**MRB PASS @** `abcdef0123456789abcdef0123456789abcdef01`\n")
    parts.append("\nDuplicates closed: none\n")
    return "".join(parts)


def test_fr8107_fat_board_with_verdict_pass_is_found():
    body = _fat_pass_board(with_verdict=True)
    assert len(body) > 500
    # Verdict appears after index 400 from the ## MRB board header.
    header_at = body.lower().index("## mrb board")
    verdict_at = body.index("**Verdict:** PASS")
    assert verdict_at - header_at > 400
    comments = [
        {
            "user": {"login": "flamingo-17680"},
            "author_association": "NONE",
            "body": body,
            "created_at": "2026-11-17T17:45:00Z",
        }
    ]
    assert gate.find_mrb_pass_board(comments) is not None
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is True, reason
    assert reason == ""


def test_fr8107_fat_board_pass_at_sha_without_nearby_verdict():
    """Alternate marker: MRB PASS @ <sha> after a long board still counts."""
    body = _fat_pass_board(with_verdict=False, with_pass_at=True)
    comments = [
        {
            "user": {"login": "flamingo-17680"},
            "author_association": "NONE",
            "body": body,
            "created_at": "2026-11-17T17:46:00Z",
        }
    ]
    assert gate.find_mrb_pass_board(comments) is not None
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is True, reason


def test_fr8107_short_board_still_passes():
    comments = [
        {
            "user": {"login": "x"},
            "author_association": "NONE",
            "body": "## MRB board\n\n**Verdict:** PASS\n",
            "created_at": "2026-11-17T17:47:00Z",
        }
    ]
    assert gate.find_mrb_pass_board(comments) is not None
