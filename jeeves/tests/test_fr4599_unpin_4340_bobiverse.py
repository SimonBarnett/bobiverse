"""FR #4599: bobiverse #4340 must stay unpinned (never require_machine=ionos).

Simon rule 2026-10-14: bobiverse work is never pinned to ionos. Same class as
#4422 / #4343 / #4512. Hard unpin wins over sticky queue stamps and soft cues.
"""
from __future__ import annotations

import gitclaim

REPO = "SimonBarnett/bobiverse"

_FR4340_TITLE = (
    "ionos !build runner install lags main (missing FR #4316 autofile on LiveStateTouched)"
)
_FR4340_BODY = """## What
installed ionos Jeeves runner at C:\\ai\\jeeves\\scripts\\run_bobiverse_build.py was checkout behind main.

## Fix
Hotpatch or ff-update the ionos Jeeves install tree so common/scripts/run_bobiverse_build.py
includes file_runner_abort_blocker from #4324.
"""


def test_fr4599_4340_in_hard_unpins_not_pins():
    assert ("simonbarnett/bobiverse", "#4340") in gitclaim._REQUIRE_MACHINE_ISSUE_UNPINS
    assert ("simonbarnett/bobiverse", "#4340") not in gitclaim._REQUIRE_MACHINE_ISSUE_PINS


def test_fr4599_4340_infer_empty_despite_ionos_bang_build_title():
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body=_FR4340_BODY,
            labels=("via-intake",),
            repo=REPO,
            ident="#4340",
        )
        == ""
    )


def test_fr4599_4340_stamp_clears_sticky_ionos_to_any():
    row = {
        "repo": REPO,
        "id": "#4340",
        "title": _FR4340_TITLE,
        "body": _FR4340_BODY,
        "require_machine": "ionos",
        "labels": ["via-intake"],
    }
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "any"
    assert gitclaim.row_require_machine(row) == ""


def test_fr4599_bobiverse_descriptive_ionos_title_does_not_pin_other_ids():
    """FR #4512: soft cues never pin bobiverse; descriptive ionos+!build is not affinity."""
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body="",
            labels=("via-intake",),
            repo=REPO,
            ident="#9994340",
        )
        == ""
    )


def test_fr4599_needs_ionos_label_still_pins_bobiverse():
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body="",
            labels=("needs-ionos",),
            repo=REPO,
            ident="#9994341",
        )
        == "ionos"
    )
