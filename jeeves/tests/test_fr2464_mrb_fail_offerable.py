"""FR #2464: mrb-fail remediation issues are offerable FRs; mrb-pass / mrb-home stay skipped."""
from __future__ import annotations

import gitclaim


def test_mrb_fail_alone_is_offerable():
    assert "mrb-fail" not in gitclaim.SKIP_FR_LABELS
    assert "mrb_fail" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL", labels=("mrb-fail",)) is None
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL", labels=("mrb_fail", "feature-request")) is None


def test_mrb_plus_mrb_fail_is_offerable():
    """agentic_fomprep #11/#42 shape: labels mrb + mrb-fail."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB FAIL board",
            labels=("mrb", "mrb-fail"),
        )
        is None
    )


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


def test_mrb_fail_enqueues_from_payload():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 11,
                "title": "MRB FAIL",
                "body": "fix the product",
                "state": "open",
                "labels": [
                    {"name": "mrb"},
                    {"name": "mrb-fail"},
                    {"name": "feature-request"},
                ],
            },
        },
    )
    assert claim is not None
    assert claim.task == "FR"
    assert claim.id in ("#11", "11", 11) or str(claim.id).endswith("11")


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
