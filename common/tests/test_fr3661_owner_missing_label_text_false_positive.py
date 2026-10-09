"""FR #3661: label_text must not refuse MRB of PRs that merely mention owner-missing.

Class of FR #987: empty-label title scan hid real work. PR #3659 title contained
the skip token ``owner-missing`` while GitHub labels were empty, so !assign MRB
refused ``label_text:owner-missing``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gitclaim  # noqa: E402


def test_fr3661_mention_owner_missing_in_title_not_label_text():
    title = "FR-3658: harvest hold titles are SKIP_FR; ensure owner-missing label"
    assert gitclaim.issue_skip_fr_reason(title=title, body="", labels=()) is None
    assert "owner-missing" not in gitclaim.SKIP_FR_LABELS_IN_TEXT


def test_fr3661_owner_missing_label_still_authoritative():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="anything mentioning nothing special",
            labels=("owner-missing", "via-intake"),
        )
        == "label:owner-missing"
    )


def test_fr3661_hold_title_still_skipped_without_labels():
    title = "harvest: hold for SimonBarnett/iphone-text-bridge - lesson"
    assert (
        gitclaim.issue_skip_fr_reason(title=title, labels=())
        == "owner_missing_hold_title"
    )


def test_fr3661_assign_row_shape_not_refused_on_remediation_title():
    """Mirror the refuse path: row_skip_fr_reason on an unlabeled MRB-shaped row."""
    row = {
        "task": "MRB",
        "repo": "simonbarnett/bobiverse",
        "id": "#3659",
        "title": "FR-3658: harvest hold titles are SKIP_FR; ensure owner-missing label",
        "labels": [],
        "state": "open",
    }
    assert gitclaim.row_skip_fr_reason(row) is None
