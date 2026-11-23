"""FR #9038: agent-CLI nonzero-exit intake receipts are not offerable FR jobs."""
from __future__ import annotations

import gitclaim


def test_cli_nonzero_exit_title_is_skip_fr():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="bug: agent CLI nonzero exit (FR #7593)",
            labels=("via-intake",),
            body="What: the agent CLI process exited non-zero.",
        )
        == "cli_exit_receipt"
    )


def test_real_fr_that_mentions_the_receipt_stays_offerable():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: stop offering agent CLI exit receipts",
            body="See bug: agent CLI nonzero exit (FR #7593)",
            labels=("feature-request",),
        )
        is None
    )


def test_cli_exit_receipt_is_not_enqueued():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 9038,
                "title": "bug: agent CLI nonzero exit (FR #7593)",
                "body": "end=cli-failure exit_code=4294967295",
                "state": "open",
                "labels": [{"name": "via-intake"}],
            },
        },
    )
    assert claim is None
