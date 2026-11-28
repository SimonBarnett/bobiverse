"""FR #10239: via-intake GIVEUP/NACK receipts are not offerable FR jobs."""
from __future__ import annotations

import gitclaim


def test_giveup_receipt_titles_are_skip_fr():
    for title in (
        "FR #10119 GIVEUP: require_machine=ionos pin, worker on redqueen",
        "FR #10227 (GIVEUP triage): ionos-pinned FR #10119 offered to redqueen",
        "Chair offered GIVEUP receipt #10227 as FR job with no code scope",
        "FIX #77 NACK: worktree-create-failed",
    ):
        assert (
            gitclaim.issue_skip_fr_reason(
                title=title,
                body="_via-intake id=`in_x` ts=`2026-11-28T05:00:59Z`_",
                labels=("feature-request", "via-intake"),
            )
            == "giveup_receipt"
        ), title


def test_giveup_receipt_without_via_intake_is_not_skipped_here():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR #10119 GIVEUP: require_machine=ionos pin",
            labels=("feature-request",),
        )
        is None
    )


def test_real_fr_mentioning_giveup_stays_offerable():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="Bug: GIVEUP cooldown never clears after a DONE",
            labels=("via-intake",),
        )
        is None
    )
