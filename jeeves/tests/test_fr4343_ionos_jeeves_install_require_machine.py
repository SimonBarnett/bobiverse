"""FR #4343 / #4599: bobiverse soft title/body cues do not pin to ionos.

Simon rule (2026-10-14 / FR #4512): bobiverse work is never pinned by title/body
text cues. Meta FR #4343 stays hard-unpinned. Product FR #4340 is also hard-
unpinned (FR #4599) — descriptive ``ionos !build`` titles are not affinity pins.

Non-bobiverse repos may still match the ionos soft cues below.
"""
from __future__ import annotations

import gitclaim

REPO = "SimonBarnett/bobiverse"
OTHER = "SimonBarnett/a-search"

_FR4340_TITLE = (
    "ionos !build runner install lags main (missing FR #4316 autofile on LiveStateTouched)"
)
_FR4340_BODY = """## What
installed ionos Jeeves runner at C:\\ai\\jeeves\\scripts\\run_bobiverse_build.py was checkout behind main.

## Fix
Hotpatch or ff-update the ionos Jeeves install tree so common/scripts/run_bobiverse_build.py
includes file_runner_abort_blocker from #4324.
"""


def test_fr4343_bobiverse_title_ionos_bang_build_does_not_pin():
    """FR #4512: bobiverse soft cues never pin."""
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body="",
            repo=REPO,
            ident="#9990",
        )
        == ""
    )


def test_fr4343_bobiverse_body_hotpatch_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="runner lags main",
            body=_FR4340_BODY,
            repo=REPO,
            ident="#9991",
        )
        == ""
    )


def test_fr4343_non_bobiverse_title_ionos_bang_build_still_pins():
    """Soft cues remain for product repos that are not bobiverse."""
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body="",
            repo=OTHER,
            ident="#9990",
        )
        == "ionos"
    )


def test_fr4343_4340_hard_unpinned():
    """FR #4599 supersedes the old hard pin of #4340."""
    assert ("simonbarnett/bobiverse", "#4340") not in gitclaim._REQUIRE_MACHINE_ISSUE_PINS
    assert ("simonbarnett/bobiverse", "#4340") in gitclaim._REQUIRE_MACHINE_ISSUE_UNPINS
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            repo=REPO,
            ident="#4340",
        )
        == ""
    )
    row = {"repo": REPO, "id": "#4340", "title": "", "body": ""}
    assert gitclaim.row_require_machine(row) == ""


def test_fr4343_meta_issue_stays_unpinned():
    """This FR (#4343) is NOT chair-only — any seat may implement the cue fix."""
    assert ("simonbarnett/bobiverse", "#4343") in gitclaim._REQUIRE_MACHINE_ISSUE_UNPINS
    title = "chair offered ionos-only FR #4340 to marchhare (missing needs-ionos stamp)"
    assert (
        gitclaim.infer_require_machine(
            title=title,
            body="No needs-ionos stamp was present on #4340.",
            repo=REPO,
            ident="#4343",
        )
        == ""
    )
    row = {
        "repo": REPO,
        "id": "#4343",
        "title": title,
        "body": "Fix require_machine cues.",
        "require_machine": "ionos",
    }
    assert gitclaim.row_require_machine(row) == ""


def test_fr4343_unrelated_hotpatch_bob_on_marchhare_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="hotpatch bob ear on marchhare",
            body="Copy bob scripts then Restart-Service ircBob.",
            repo=REPO,
            ident="#9992",
        )
        == ""
    )
