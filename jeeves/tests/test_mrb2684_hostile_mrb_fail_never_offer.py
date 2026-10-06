"""MRB #2684 hostile: mrb-fail never offer + global needs_human after GIVEUP threshold."""
from __future__ import annotations

import gitclaim


def test_mrb2684_verdict_title_case_and_spacing():
    assert gitclaim.issue_skip_fr_reason(title="mrb fail: board", labels=()) == "mrb_verdict_title"
    assert gitclaim.issue_skip_fr_reason(title="MRB  PASS: spaced", labels=()) == "mrb_verdict_title"


def test_mrb2684_verdict_title_dash_form_skip_fr2687():
    """FR #2687 closed the colon-only gap: dash form is also SKIP_FR."""
    assert (
        gitclaim.issue_skip_fr_reason(title="MRB FAIL - dash form", labels=())
        == "mrb_verdict_title"
    )


def test_mrb2684_giveup_count_string_coerces():
    row = {
        "needs_human": True,
        "giveup_count": str(gitclaim.GIVEUP_NEEDS_HUMAN_COUNT),
        "giveup_seats": "marchhare-1",
    }
    assert gitclaim.row_needs_human(row, "ionos-99") is True


def test_mrb2684_fomprep11_pin_and_label_both_skip():
    assert ("simonbarnett/agentic_fomprep", "#11") in gitclaim._SKIP_FR_ISSUE_PINS
    assert gitclaim.issue_skip_fr_reason(
        title="anything",
        labels=("mrb-fail", "via-intake"),
    ).startswith("label:")


def test_mrb2684_mrb_fail_blocks_repo_uat():
    """Verdict boards must not hold product UAT (SKIP_FR => not blocking)."""
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="MRB FAIL: formlimited",
            labels=("mrb", "mrb-fail"),
        )
        is False
    )


def test_mrb2684_commands_doc_lists_mrb_fail_skip():
    from pathlib import Path
    from repo_layout import resolve

    text = resolve("jeeves/docs/jeeves-commands.md").read_text(encoding="utf-8")
    assert "mrb-fail" in text
    assert "SKIP_FR" in text
    # FR #2562 global giveup note present after docs PR
    assert "2562" in text or "2677" in text or "giveup_count" in text.lower()
