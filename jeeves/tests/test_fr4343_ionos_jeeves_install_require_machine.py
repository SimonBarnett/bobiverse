"""FR #4343: ionos !build / Jeeves install hotpatch|ff-update cues pin require_machine=ionos.

#4340 was offered to marchhare without needs-ionos. Title/body host cues must stamp
before offer. Meta FR #4343 itself stays unpinned (any fleet seat).
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


def test_fr4343_title_ionos_bang_build_pins_ionos():
    assert (
        gitclaim.infer_require_machine(
            title=_FR4340_TITLE,
            body="",
            repo=REPO,
            ident="#9990",
        )
        == "ionos"
    )


def test_fr4343_body_hotpatch_ionos_jeeves_install_pins_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="runner lags main",
            body=_FR4340_BODY,
            repo=REPO,
            ident="#9991",
        )
        == "ionos"
    )


def test_fr4343_hard_pin_4340():
    assert ("simonbarnett/bobiverse", "#4340") in gitclaim._REQUIRE_MACHINE_ISSUE_PINS
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            repo=REPO,
            ident="#4340",
        )
        == "ionos"
    )
    row = {"repo": REPO, "id": "#4340", "title": "", "body": ""}
    assert gitclaim.row_require_machine(row) == "ionos"


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
