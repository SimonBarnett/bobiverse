"""FR #2562 / #2677: reverse #2464 — mrb-fail verdict boards are NEVER offerable FRs.

Kept under the old filename so historical MRB/hostile references still resolve;
assertions now match the never-offer policy (remediation belongs on child FRs).
"""
from __future__ import annotations

import gitclaim


def test_mrb_fail_alone_is_skipped():
    assert "mrb-fail" in gitclaim.SKIP_FR_LABELS
    assert "mrb_fail" in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL", labels=("mrb-fail",)).startswith(
        "label:"
    )
    assert gitclaim.issue_skip_fr_reason(
        title="MRB FAIL", labels=("mrb_fail", "feature-request")
    ).startswith("label:")


def test_mrb_plus_mrb_fail_is_skipped():
    """agentic_fomprep #11/#42 shape: labels mrb + mrb-fail → skip (do not drop bare mrb)."""
    reason = gitclaim.issue_skip_fr_reason(
        title="MRB FAIL board",
        labels=("mrb", "mrb-fail"),
    )
    assert reason is not None
    assert reason.startswith("label:")


def test_mrb_pass_still_skipped():
    assert gitclaim.issue_skip_fr_reason(title="MRB PASS", labels=("mrb-pass",)) == "label:mrb-pass"
    assert gitclaim.issue_skip_fr_reason(title="MRB PASS", labels=("mrb_pass",)) == "label:mrb_pass"


def test_mrb_home_still_skipped():
    """agentic_fomprep #7/#8 shape until mrb-home label removed."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: skills catalog",
            labels=("feature-request", "mrb-home"),
        )
        == "label:mrb-home"
    )


def test_bare_mrb_without_fail_still_skipped():
    assert gitclaim.issue_skip_fr_reason(title="MRB board", labels=("mrb",)) == "label:mrb"


def test_mrb_fail_does_not_enqueue_from_payload():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 11,
                "title": "MRB FAIL",
                "body": "verdict board — remediation is on child FRs",
                "state": "open",
                "labels": [
                    {"name": "mrb"},
                    {"name": "mrb-fail"},
                    {"name": "feature-request"},
                ],
            },
        },
    )
    assert claim is None


def test_mrb_pass_still_does_not_enqueue():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 20,
                "title": "MRB PASS receipt",
                "body": "",
                "state": "open",
                "labels": [{"name": "mrb-pass"}, {"name": "feature-request"}],
            },
        },
    )
    assert claim is None
