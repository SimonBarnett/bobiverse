"""FR #2521: agentic_fomprep#11 is FAIL remediation — not a hard-pin umbrella."""
from __future__ import annotations

import gitclaim as gc


def test_fr2521_fomprep11_not_in_skip_pins_homes_remain():
    pins = {(r, i) for r, i in gc._SKIP_FR_ISSUE_PINS}
    assert ("simonbarnett/agentic_fomprep", "#11") not in pins
    for n in ("#3", "#7", "#8", "#9", "#20"):
        assert ("simonbarnett/agentic_fomprep", n) in pins


def test_fr2521_row_skip_11_not_hard_pin_while_homes_are():
    assert gc.row_skip_fr_reason({"repo": "SimonBarnett/agentic_fomprep", "id": "#11", "title": "remediate FAIL", "labels": []}) != "hard_pin_umbrella"
    assert gc.row_skip_fr_reason({"repo": "SimonBarnett/agentic_fomprep", "id": "#8", "title": "MRB home", "labels": []}) == "hard_pin_umbrella"
