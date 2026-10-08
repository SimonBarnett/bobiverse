"""FR #3658: owner-missing harvest holds must not be offered as FR.

Regression from bobiverse#3657: intake titled the hold ``harvest: hold for …`` but
``owner-missing`` was not a repo label, so GhCliFiler retried create with empty
labels. FR #1682 then treated the ``harvest:`` title as an offerable promote FR.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gitclaim  # noqa: E402
import intake  # noqa: E402


def test_fr3658_hold_title_skips_fr_with_empty_labels():
    title = (
        "harvest: hold for SimonBarnett/iphone-text-bridge - harvest: FR "
        "bobiverse#3096 GIVEUP: iphone-text-bridge still 404"
    )
    reason = gitclaim.issue_skip_fr_reason(title=title, body="", labels=())
    assert reason == "owner_missing_hold_title"


def test_fr3658_plain_harvest_title_still_offerable():
    # FR #1682 carve-out: promote harvest: titles stay offerable.
    assert (
        gitclaim.issue_skip_fr_reason(
            title="harvest: lesson from session",
            body="",
            labels=("via-intake", "skill"),
        )
        is None
    )


def test_fr3658_owner_missing_label_still_skips():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="anything",
            labels=(intake.OWNER_MISSING_LABEL, "via-intake"),
        )
        == f"label:{intake.OWNER_MISSING_LABEL}"
    )


def test_fr3658_intake_hold_skip_even_if_labels_dropped(tmp_path: Path):
    """If create_issue returned the hold title but lost labels, chair still skips."""
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/iphone-text-bridge",
            "title": "harvest: Shortcuts all-SMS recipe",
            "body": (
                "Session summary:\niphone-text-bridge\n\n"
                "Lessons:\n- Shortcuts all-SMS recipe for the bridge\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3658_hold")
    assert rec["state"] == "held_owner_missing"
    issue = filer.issues[-1]
    # Simulate gh_filer unlabeled fallback (labels wiped).
    reason = gitclaim.issue_skip_fr_reason(
        title=issue["title"],
        body=issue.get("body") or "",
        labels=(),
    )
    assert reason == "owner_missing_hold_title"
