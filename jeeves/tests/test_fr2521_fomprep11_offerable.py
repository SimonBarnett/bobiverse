"""FR #2562 / #2677: reverse #2521 — agentic_fomprep#11 is a hard-pin (MRB FAIL verdict board).

Kept under the old filename so historical MRB/hostile references still resolve.
"""
from __future__ import annotations

import gitclaim as gc


def test_fr2521_fomprep11_in_skip_pins_homes_remain():
    pins = {(r, i) for r, i in gc._SKIP_FR_ISSUE_PINS}
    assert ("simonbarnett/agentic_fomprep", "#11") in pins
    for n in ("#3", "#7", "#8", "#9", "#20"):
        assert ("simonbarnett/agentic_fomprep", n) in pins


def test_fr2521_row_skip_11_is_hard_pin_like_homes():
    assert (
        gc.row_skip_fr_reason(
            {
                "repo": "SimonBarnett/agentic_fomprep",
                "id": "#11",
                "title": "MRB FAIL: formlimited",
                "labels": [],
            }
        )
        == "hard_pin_umbrella"
    )
    assert (
        gc.row_skip_fr_reason(
            {
                "repo": "SimonBarnett/agentic_fomprep",
                "id": "#8",
                "title": "MRB home",
                "labels": [],
            }
        )
        == "hard_pin_umbrella"
    )
