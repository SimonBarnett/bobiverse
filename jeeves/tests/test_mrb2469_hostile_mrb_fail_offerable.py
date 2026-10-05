"""Hostile MRB #2469: mrb-fail offerable; mrb-home/mrb-pass still win; bare mrb alone skips."""
from __future__ import annotations

import gitclaim
from repo_layout import ROOT


def test_hostile_mrb_fail_plus_mrb_home_still_skipped():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB FAIL",
            labels=("mrb", "mrb-fail", "mrb-home"),
        )
        == "label:mrb-home"
    )


def test_hostile_mrb_fail_plus_mrb_pass_still_skipped():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB FAIL then PASS?",
            labels=("mrb", "mrb-fail", "mrb-pass"),
        )
        == "label:mrb-pass"
    )


def test_hostile_claim_task_is_fr_not_mrb_for_fail_remediation():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 42,
                "title": "MRB FAIL product",
                "body": "fix it",
                "state": "open",
                "labels": [{"name": "mrb"}, {"name": "mrb-fail"}],
            },
        },
    )
    assert claim is not None
    assert claim.task == "FR"
    assert claim.id == "#42"
    assert (claim.line or "") == ""


def test_hostile_skip_set_mentions_2464():
    src = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    assert "FR #2464" in src
    assert "mrb-fail" not in gitclaim.SKIP_FR_LABELS
