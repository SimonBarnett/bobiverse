"""FR #987: label_text skip must not hide real FRs that merely mention skip words."""
from __future__ import annotations

import gitclaim


def test_labeled_fr_mentioning_mrb_home_in_title_is_kept():
    """Live bug: #782 title '...skip for stale mrb-home rows' + feature-request labels."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="UAT #271: verify/deploy mrb-home skip on live ionos chair",
            body="deploy the skip for stale mrb-home rows",
            labels=("feature-request", "via-intake"),
        )
        is None
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: chair should skip for stale mrb-home rows in queue",
            body="fix the text scan",
            labels=("feature-request",),
        )
        is None
    )


def test_labeled_fr_mentioning_evergreen_in_body_is_kept():
    """Live bug: #610 body mentions evergreen; GitHub labels are real FRs."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="UAT #271: verify/deploy mrb-home skip on live ionos chair (compose/recycle)",
            body="These boards are evergreen and must stay open.",
            labels=("feature-request", "via-intake"),
        )
        is None
    )


def test_legacy_empty_labels_still_skip_mrb_home_in_title_line():
    assert gitclaim.issue_skip_fr_reason(
        title="mrb-home board for fleet",
        body="",
        labels=(),
    ) == "label_text:mrb-home"
    assert gitclaim.row_skip_fr_reason(
        {"line": "evergreen board leftover", "labels": (), "title": ""}
    ) == "label_text:evergreen"


def test_label_text_does_not_scan_body_even_without_labels():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: real work item",
            body="mentions mrb-home and evergreen in the narrative only",
            labels=(),
        )
        is None
    )


def test_real_mrb_home_label_still_skipped():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="Anything",
            labels=("mrb-home", "mrb"),
        )
        == "label:mrb-home"
        or gitclaim.issue_skip_fr_reason(title="Anything", labels=("mrb-home", "mrb")).startswith(
            "label:"
        )
    )


def test_evergreen_title_shape_title_only_not_body():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="Hostile MRB home: bobiverse handoff",
            body="",
            labels=(),
        )
        == "evergreen_mrb_home"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: document board process",
            body="See Hostile MRB home boards for handoff notes.",
            labels=("feature-request",),
        )
        is None
    )


def test_assign_row_accepts_labeled_fr_with_mrb_home_mention(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#782",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#782",
                    "title": "FR: skip for stale mrb-home rows should not hide this",
                    "body": "evergreen wording in body only",
                    "labels": ["feature-request", "via-intake"],
                    "state": "open",
                }
            ],
            "accepted": [],
        },
    )
    assert gitclaim.row_skip_fr_reason(gitclaim.load_unaccepted(tmp_path)[0]) is None
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#782"