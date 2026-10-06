"""Hostile MRB #2692: dash-form MRB verdict title edges (FR #2687)."""
from __future__ import annotations

import gitclaim


def test_mrb2692_claim_payload_dash_fail_skipped():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 99,
                "title": "MRB FAIL - formlimited board",
                "body": "verdict",
                "state": "open",
                "labels": [],
            },
        },
    )
    assert claim is None


def test_mrb2692_real_fr_prefix_still_offerable():
    assert (
        gitclaim.issue_skip_fr_reason(title="FR: MRB FAIL - mention in prose", labels=())
        is None
    )


def test_mrb2692_emdash_en_dash_residual_not_matched():
    """ASCII hyphen/colon only (FR letter). Unicode dashes remain ACCEPTABLE residual."""
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL — emdash", labels=()) is None
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL – endash", labels=()) is None


def test_mrb2692_regex_source_mentions_2687():
    from repo_layout import resolve

    src = resolve("common/scripts/gitclaim.py").read_text(encoding="utf-8")
    assert "2687" in src
    assert r"[-:]" in src or "[-:]" in src
