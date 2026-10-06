"""Hostile MRB #2685: via-intake CRITICAL: offerable; shapes + bare CRITICAL stay spam.

Also locks coexistence with FR #2562/#2677 (mrb-fail / MRB FAIL: still skipped).
"""
from __future__ import annotations

import gitclaim


def test_hostile_claim_payload_via_intake_critical_enqueues():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 2670,
                "title": "CRITICAL: chair deadlock real work",
                "body": "via intake product",
                "state": "open",
                "labels": [{"name": "via-intake"}],
            },
        },
    )
    assert claim is not None
    assert claim.task == "FR"
    assert claim.id == "#2670"


def test_hostile_claim_payload_bare_critical_skipped():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 99,
                "title": "CRITICAL: Jeeves chair DOWN again",
                "body": "",
                "state": "open",
                "labels": [],
            },
        },
    )
    assert claim is None


def test_hostile_shape_beats_via_intake():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="CRITICAL: 2nd re-offer of agentic_fomprep#11",
            labels=("via-intake", "feature-request"),
        )
        == "critical_spam_title"
    )


def test_hostile_backcompat_critical_spam_title_re_still_matches_prefix():
    assert gitclaim.CRITICAL_SPAM_TITLE_RE.search("CRITICAL: anything")
    assert gitclaim.CRITICAL_SPAM_PREFIX_RE.search("CRITICAL: anything")
    assert gitclaim.CRITICAL_SPAM_SHAPE_RE.search("CRITICAL: 3rd re-offer of x")


def test_hostile_mrb_fail_still_skipped_after_2670_coexist():
    """#2562 on main: mrb-fail / MRB FAIL: remain never-offerable alongside #2670."""
    assert "mrb-fail" in gitclaim.SKIP_FR_LABELS
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB FAIL: formlimited",
            labels=("via-intake",),
        )
        == "mrb_verdict_title"
    )
    assert gitclaim.issue_skip_fr_reason(
        title="CRITICAL: re-offered fomprep verdict",
        labels=("via-intake", "mrb-fail"),
    ).startswith("label:")
