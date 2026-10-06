"""FR #2687: MRB FAIL/PASS dash-form verdict titles are SKIP_FR (widen colon-only regex)."""
from __future__ import annotations

import re

import gitclaim


def test_fr2687_dash_form_fail_skip():
    assert (
        gitclaim.issue_skip_fr_reason(title="MRB FAIL - dash form", labels=())
        == "mrb_verdict_title"
    )


def test_fr2687_dash_form_pass_skip():
    assert (
        gitclaim.issue_skip_fr_reason(title="MRB PASS - board", labels=())
        == "mrb_verdict_title"
    )


def test_fr2687_dash_form_case_and_spacing():
    assert gitclaim.issue_skip_fr_reason(title="mrb fail - board", labels=()) == "mrb_verdict_title"
    assert gitclaim.issue_skip_fr_reason(title="MRB  FAIL-nospace", labels=()) == "mrb_verdict_title"


def test_fr2687_colon_form_still_skip():
    assert gitclaim.issue_skip_fr_reason(title="MRB FAIL: still", labels=()) == "mrb_verdict_title"
    assert gitclaim.issue_skip_fr_reason(title="MRB PASS: still", labels=()) == "mrb_verdict_title"


def test_fr2687_non_verdict_title_still_offerable():
    """Real FR titles that mention MRB must stay offerable."""
    assert gitclaim.issue_skip_fr_reason(title="harden MRB/FR routing", labels=()) is None
    assert gitclaim.issue_skip_fr_reason(title="MRB checklist as FR", labels=()) is None


def test_fr2687_dash_does_not_block_uat():
    assert (
        gitclaim.issue_blocks_repo_uat(title="MRB FAIL - formlimited", labels=())
        is False
    )


def test_fr2687_regex_accepts_dash_or_colon():
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB FAIL - x")
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB PASS: x")
    assert not re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB FAIL x")  # needs separator
