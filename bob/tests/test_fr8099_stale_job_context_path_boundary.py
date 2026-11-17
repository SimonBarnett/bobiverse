"""FR #8099: stale_job_context number/leaf match uses path boundaries.

``fr-80910`` must not satisfy offer ``#8091`` / leaf ``fr-8091`` (substring false match).
"""
from __future__ import annotations

import bob_worker as bw

KEY = "FR SimonBarnett/bobiverse#8091"


def test_fr8099_fr_80910_worktree_is_stale_for_offer_8091():
    assert (
        bw.stale_job_context_reason(
            KEY,
            worktree=r"C:\wt\bobiverse\fr-80910",
            outbox=r"C:\wt\bobiverse\fr-80910\.bob\outbox.txt",
        )
        == "stale_job_context"
    )


def test_fr8099_fr_8091_worktree_still_matches():
    assert (
        bw.stale_job_context_reason(
            KEY,
            worktree=r"C:\wt\bobiverse\fr-8091",
            outbox=r"C:\wt\bobiverse\fr-8091\.bob\outbox.txt",
            text="FINISH FR SimonBarnett/bobiverse#8091 Closes SimonBarnett/bobiverse#8091",
            branch="fr-8091",
        )
        == ""
    )


def test_fr8099_text_and_branch_reject_prefix_false_match():
    assert (
        bw.stale_job_context_reason(
            KEY,
            text="FINISH FR SimonBarnett/bobiverse#80910 on fr-80910",
            branch="fr-80910",
        )
        == "stale_job_context"
    )
