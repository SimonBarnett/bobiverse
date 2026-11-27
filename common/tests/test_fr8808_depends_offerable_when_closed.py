# -*- coding: utf-8 -*-
"""FR #8808 / BOB-D4 S1: offerable when all Depends-on issues are CLOSED.

D3 skips while any depend is OPEN. This slice pins the flip: after the last
open depend closes (queue key gone / state=closed / issue_open False),
``row_depends_open_reason`` returns None so the FR is offerable again.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

REPO = "SimonBarnett/bobiverse"


def _fr(num: int, body: str, *, state: str = "open") -> dict:
    return {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "title": f"FR {num}",
        "body": body,
        "state": state,
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
    }


def test_fr8808_open_keys_flip_closed_clears_depends_open():
    """S1: depend in open_keys blocks; after close (not in keys) gate clears."""
    blocked = _fr(3, "Depends-on: #5\n")
    open_keys = {(REPO.lower(), 5)}
    assert gitclaim.row_depends_open_reason(blocked, open_keys) == gitclaim.DEPENDS_OPEN_REASON

    # Flip: depend CLOSED. Absence alone is unknown (FR #10059); the checker says closed.
    open_keys_after = set()
    assert (
        gitclaim.row_depends_open_reason(
            blocked, open_keys_after, issue_open=lambda repo, num: False
        )
        is None
    )


def test_fr8808_queue_state_closed_drops_from_open_fr_issue_keys():
    """open_fr_issue_keys ignores state=closed so a closed depend unblocks."""
    dep_open = _fr(5, "Depends-on: (none)\n", state="open")
    dep_closed = _fr(5, "Depends-on: (none)\n", state="closed")
    blocked = _fr(3, "Depends-on: #5\n")
    doc_open = {"unaccepted": [blocked], "accepted": [dep_open], "done": []}
    doc_closed = {"unaccepted": [blocked], "accepted": [dep_closed], "done": []}

    keys_open = gitclaim.open_fr_issue_keys(doc_open)
    assert (REPO.lower(), 5) in keys_open
    assert gitclaim.row_depends_open_reason(blocked, keys_open) == gitclaim.DEPENDS_OPEN_REASON

    keys_closed = gitclaim.open_fr_issue_keys(doc_closed)
    assert (REPO.lower(), 5) not in keys_closed
    assert (
        gitclaim.row_depends_open_reason(
            blocked, keys_closed, issue_open=lambda repo, num: False
        )
        is None
    )


def test_fr8808_issue_open_checker_flip_false_clears_gate():
    """S1 live checker: True blocks; False after close clears (fail-when: stays skipped)."""
    blocked = _fr(3, "Depends-on: SimonBarnett/other#77\n")
    # row_depends_open_reason passes lower-cased repo keys to issue_open.
    open_map = {"simonbarnett/other#77": True}

    def issue_open(repo: str, num: str) -> bool:
        return bool(open_map.get(f"{repo}#{num}", False))

    assert (
        gitclaim.row_depends_open_reason(blocked, set(), issue_open=issue_open)
        == gitclaim.DEPENDS_OPEN_REASON
    )

    open_map["simonbarnett/other#77"] = False
    assert gitclaim.row_depends_open_reason(blocked, set(), issue_open=issue_open) is None


def test_fr8808_all_depends_closed_when_mixed_refs():
    """Every listed depend must be closed; one remaining OPEN still blocks."""
    blocked = _fr(3, "Depends-on: #5, SimonBarnett/other#7\n")
    # #5 closed (absent), #7 still open
    assert (
        gitclaim.row_depends_open_reason(blocked, {("simonbarnett/other", 7)})
        == gitclaim.DEPENDS_OPEN_REASON
    )
    # both closed. The checker is what proves closed (FR #10059).
    assert (
        gitclaim.row_depends_open_reason(
            blocked, set(), issue_open=lambda repo, num: False
        )
        is None
    )


def test_fr8808_8754_index_skips_closed_so_blocked_reason_clears():
    """BOB-D4: row_fr_depends_blocked_reason must clear when depend stamps state=closed."""
    dep = _fr(5, "Depends-on: (none)\n", state="open")
    blocked = _fr(3, "Depends-on: #5\n")
    doc = {"unaccepted": [blocked], "accepted": [dep], "done": []}
    why = gitclaim.row_fr_depends_blocked_reason(blocked, doc)
    assert why and "depends-on open" in why

    dep["state"] = "closed"
    assert gitclaim.row_fr_depends_blocked_reason(blocked, doc) is None
