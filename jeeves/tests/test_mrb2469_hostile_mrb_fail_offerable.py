"""Hostile MRB #2469 inverted by FR #2562 / #2677: mrb-fail never offerable.

mrb-home / mrb-pass still win; bare mrb alone skips; claim_from_payload returns None.
"""
from __future__ import annotations

import gitclaim
from repo_layout import ROOT


def test_hostile_mrb_fail_plus_mrb_home_still_skipped():
    reason = gitclaim.issue_skip_fr_reason(
        title="MRB FAIL",
        labels=("mrb", "mrb-fail", "mrb-home"),
    )
    assert reason is not None and reason.startswith("label:")


def test_hostile_mrb_fail_plus_mrb_pass_still_skipped():
    reason = gitclaim.issue_skip_fr_reason(
        title="MRB FAIL then PASS?",
        labels=("mrb", "mrb-fail", "mrb-pass"),
    )
    assert reason is not None and reason.startswith("label:")


def test_hostile_claim_mrb_fail_is_none():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 42,
                "title": "MRB FAIL product",
                "body": "verdict board",
                "state": "open",
                "labels": [{"name": "mrb"}, {"name": "mrb-fail"}],
            },
        },
    )
    assert claim is None


def test_hostile_skip_set_mentions_2562_and_includes_mrb_fail():
    src = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    assert "FR #2562" in src
    assert "mrb-fail" in gitclaim.SKIP_FR_LABELS
    assert "mrb_fail" in gitclaim.SKIP_FR_LABELS
