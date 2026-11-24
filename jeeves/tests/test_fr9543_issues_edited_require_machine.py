"""FR #9543: issues.edited refreshes require_machine pin; #9526 hard-pinned."""
from __future__ import annotations

import gitclaim


def test_fr9543_issues_edited_claim_carries_body_pin():
    payload = {
        "action": "edited",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 9526,
            "title": "marchhare: still NACK engine.alive stale after #9525 merge",
            "body": (
                "Host tray not on tip.\n\n"
                "require_machine: marchhare\n"
            ),
            "labels": [{"name": "feature-request"}, {"name": "via-intake"}],
            "state": "open",
        },
    }
    claim = gitclaim.claim_from_payload("issues", payload, line="")
    assert claim is not None
    assert claim.task == "FR"
    assert claim.action == "edited"
    assert "require_machine: marchhare" in claim.body
    assert (
        gitclaim.infer_require_machine(
            title=claim.title,
            body=claim.body,
            labels=claim.labels,
            repo=claim.repo,
            ident=claim.id,
        )
        == "marchhare"
    )


def test_fr9543_edited_closed_issue_is_noop():
    payload = {
        "action": "edited",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 1,
            "title": "x",
            "body": "require_machine: marchhare\n",
            "labels": [],
            "state": "closed",
        },
    }
    assert gitclaim.claim_from_payload("issues", payload, line="") is None


def test_fr9543_duplicate_refresh_updates_body_and_blocks_wrong_shop(tmp_path):
    home = tmp_path
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9526",
                "title": "marchhare: still NACK",
                "body": "old body without pin",
                "seq": 1,
            }
        ],
        "accepted": [],
        "done": [],
    }
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#9526",
        event="issues",
        action="edited",
        line="",
        title="marchhare: still NACK",
        body="evidence...\n\nrequire_machine: marchhare\n",
        labels=["feature-request"],
        state="open",
    )
    assert gitclaim._append_unaccepted(doc, claim) == "duplicate"
    row = doc["unaccepted"][0]
    assert "require_machine: marchhare" in str(row.get("body") or "")
    assert gitclaim.row_require_machine(row) == "marchhare"
    assert gitclaim.row_blocked_for_machine(row, "redqueen-668") is True
    assert gitclaim.row_blocked_for_machine(row, "flamingo-17068") is True
    assert gitclaim.row_blocked_for_machine(row, "marchhare-1") is False


def test_fr9543_hard_pin_9526_even_without_body():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9526",
        "title": "marchhare: still NACK",
        "body": "stale truncated body",
    }
    assert gitclaim.row_require_machine(row) == "marchhare"
