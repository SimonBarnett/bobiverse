"""FR #4512: bobiverse rows are never pinned by title/body text cues.

Only ``needs-<machine>`` labels (and intentional dedicated ``require_machine:``
body lines / hard issue pins) may pin. Stale persisted stamps clear on stamp/resync.
"""
from __future__ import annotations

import gitclaim


def test_fr4512_title_mention_require_machine_ionos_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="Jeeves still pins bobiverse rows to require_machine=ionos",
            body="MRB #4337 and FR #4478 were refused as pinned to another machine.",
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="4512",
        )
        == ""
    )


def test_fr4512_title_mention_ce_priority_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="chair offered without require_machine=ce-priority-dev1",
            body="Living FR was offered to marchhare.",
            labels=("feature-request", "via-intake"),
            repo="SimonBarnett/bobiverse",
            ident="4427",
        )
        == ""
    )


def test_fr4512_airc_in_title_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="airc sparse bootstrap exits 0 without a .git directory",
            body="test_bootstrap_sparse_only_own_subtree_plus_common[airc-other2]",
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="4478",
        )
        == ""
    )


def test_fr4512_needs_ionos_label_still_pins():
    assert (
        gitclaim.infer_require_machine(
            title="ionos !build runner lags main",
            body="",
            labels=("needs-ionos", "bug"),
            repo="SimonBarnett/bobiverse",
            ident="9994340",
        )
        == "ionos"
    )


def test_fr4512_dedicated_body_pin_line_still_pins():
    assert (
        gitclaim.infer_require_machine(
            title="hotpatch verify on chair",
            body="Steps.\n\nrequire_machine: ionos\n",
            labels=(),
            repo="SimonBarnett/bobiverse",
            ident="999001",
        )
        == "ionos"
    )


def test_fr4512_stale_stamp_cleared_when_no_label():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "4478",
        "task": "FR",
        "title": "airc sparse bootstrap exits 0 without a .git directory",
        "body": "airc install root .git was not a directory",
        "labels": ["via-intake"],
        "require_machine": "ionos",
    }
    gitclaim._stamp_require_machine(row)
    stamped = str(row.get("require_machine") or "").strip().lower()
    assert stamped in {"", "any", "none", "*", "-"}
    assert gitclaim.row_require_machine(row) == ""


def test_fr4512_stale_stamp_kept_when_needs_label():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "id": "9994340",
        "task": "FR",
        "title": "install work",
        "body": "",
        "labels": ["needs-ionos"],
        "require_machine": "ionos",
    }
    gitclaim._stamp_require_machine(row)
    assert gitclaim.row_require_machine(row) == "ionos"


def test_fr4512_other_repo_title_cue_still_pins():
    """Non-bobiverse repos keep install-on-ionos title cues (no regression)."""
    assert (
        gitclaim.infer_require_machine(
            title="install+smoke on ionos for release pack",
            body="",
            labels=(),
            repo="SimonBarnett/a-search",
            ident="1",
        )
        == "ionos"
    )
