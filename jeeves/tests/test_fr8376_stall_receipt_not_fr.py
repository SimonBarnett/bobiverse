"""FR #8376: stall detector receipts are not offerable FR jobs."""
from __future__ import annotations

import gitclaim


def test_stall_title_is_skip_fr():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="stall:all-gave-up:SimonBarnett/bobiverse#7899",
            labels=("via-intake", "feature-request"),
        )
        == "stall_receipt"
    )
    assert gitclaim.issue_skip_fr_reason(title="stall:ack-stale:#1") == "stall_receipt"
    assert gitclaim.issue_skip_fr_reason(title="FR: a real product gap") is None


def test_stall_issue_is_not_enqueued_and_subject_row_stays():
    subject = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#7899",
        "title": "real review",
        "needs_human": False,
        "giveup_count": 2,
    }
    doc = {"v": 1, "unaccepted": [dict(subject)], "accepted": [], "done": []}
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 7914,
                "title": "stall:all-gave-up:SimonBarnett/bobiverse#7899",
                "body": "fingerprint stall:all-gave-up:SimonBarnett/bobiverse#7899",
                "state": "open",
                "labels": [{"name": "via-intake"}],
            },
        },
    )
    assert claim is None
    assert doc["unaccepted"] == [subject]
