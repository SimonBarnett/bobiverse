"""MRB #2482 hostile gates for FR #2480 agentic_fomprep MRB-home hard-pins."""
from __future__ import annotations

import gitclaim


REPO = "SimonBarnett/agentic_fomprep"
PINS = {3, 7, 8, 9, 11, 20}


def test_mrb2482_pin_set_exact_six():
    got = {
        int(ident.lstrip("#"))
        for (repo, ident) in gitclaim._SKIP_FR_ISSUE_PINS
        if repo == "simonbarnett/agentic_fomprep"
    }
    assert got == PINS


def test_mrb2482_same_numbers_on_bobiverse_not_pinned():
    for num in PINS:
        row = {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": f"#{num}",
            "title": "FR: real work",
            "labels": [],
        }
        assert gitclaim.row_skip_fr_reason(row) is None


def test_mrb2482_body_phrase_case_insensitive():
    reason = gitclaim.issue_skip_fr_reason(
        title="FR: anything",
        body="this ISSUE is the mrb HOME for THIS feature request. Opened by hostile.",
        labels=(),
    )
    assert reason == "mrb_home_board_body"


def test_mrb2482_offer_refuse_uses_hard_pin():
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8",
        "title": "FR: git as source",
        "labels": [],
        "seq": 1,
        "ts": "t",
        "line": "x",
    }
    assert gitclaim.row_skip_fr_reason(row) == "hard_pin_umbrella"
