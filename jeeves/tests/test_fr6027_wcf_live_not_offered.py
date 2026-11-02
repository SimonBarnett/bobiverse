"""FR #6027: living WCF/tabula live FR #6026 must not be offered to a random shop."""
from __future__ import annotations

import gitclaim


def test_fr6027_hard_pin_6026_is_needs_human_hold():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#6026",
        "title": "FR: airc PRIORITY over WCF as tabula",
        "labels": [],
        "body": "On HR Smith hrs-dev-live1 as tabula",
    }
    assert gitclaim.row_skip_fr_reason(row) == "needs_human_hold"
    assert ("simonbarnett/bobiverse", "#6026") in gitclaim._NEEDS_HUMAN_ISSUE_PINS


def test_fr6027_hashless_id_and_enqueue_claim_skipped():
    row = {
        "repo": "simonbarnett/bobiverse",
        "task": "FR",
        "id": "6026",
        "title": "FR: WCF",
        "labels": ["via-intake"],
    }
    assert gitclaim.row_skip_fr_reason(row) == "needs_human_hold"
    claim = gitclaim.claim_from_github_issue(
        "SimonBarnett/bobiverse",
        {
            "number": 6026,
            "title": "FR: WCF",
            "body": "hrs-dev-live1 tabula",
            "labels": [{"name": "feature-request"}],
            "state": "open",
        },
    )
    assert claim is None


def test_fr6027_other_bobiverse_fr_still_offerable():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#6027",
        "title": "chair offered FR #6026 with no pin",
        "labels": ["via-intake"],
    }
    assert gitclaim.row_skip_fr_reason(row) is None
