# -*- coding: utf-8 -*-
"""FR #8810 / BOB-D6 S1: fetch issue body when queue row body is empty before depends.

Fail-when: silent offer with empty body (Depends-on on GitHub never parsed).
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


def _fresh_cache() -> dict:
    """Per-test cache so FR_BODY_FETCH_SHARED_CACHE cannot poison assertions."""
    return {}


def test_fr8810_ensure_fetches_and_stamps_body():
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#3",
        "title": "FR 3",
        "body": "",
    }
    calls: list[tuple[str, str]] = []

    def fetch_issue(repo: str, num: str) -> dict:
        calls.append((repo, num))
        return {"number": 3, "body": "Depends-on: #5\n\nAcceptance.\n", "state": "open"}

    out = gitclaim.ensure_fr_queue_body(
        row, fetch_issue=fetch_issue, cache=_fresh_cache()
    )
    assert calls == [(REPO, "3")]
    assert "Depends-on: #5" in out
    assert "Depends-on: #5" in str(row.get("body") or "")


def test_fr8810_ensure_skips_fetch_when_body_present():
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#3",
        "body": "Depends-on: (none)\n",
    }
    calls: list[tuple[str, str]] = []

    def fetch_issue(repo: str, num: str) -> dict:
        calls.append((repo, num))
        return {"body": "SHOULD NOT USE"}

    out = gitclaim.ensure_fr_queue_body(
        row, fetch_issue=fetch_issue, cache=_fresh_cache()
    )
    assert calls == []
    assert "Depends-on: (none)" in out


def test_fr8810_ensure_non_fr_unchanged():
    row = {"repo": REPO, "task": "MRB", "id": "#9", "body": ""}
    assert (
        gitclaim.ensure_fr_queue_body(
            row, fetch_issue=lambda r, n: {"body": "x"}, cache=_fresh_cache()
        )
        == ""
    )


def test_fr8810_empty_body_fetch_exposes_depends_to_blocked_reason():
    """After hydrate, 8754/D3 gates see Depends-on from fetched body."""
    blocked = {
        "repo": REPO,
        "task": "FR",
        "id": "#3",
        "title": "FR 3",
        "body": "",
        "state": "open",
    }
    dep = {
        "repo": REPO,
        "task": "FR",
        "id": "#5",
        "title": "FR 5",
        "body": "Depends-on: (none)\n",
        "state": "open",
    }
    doc = {"unaccepted": [blocked], "accepted": [dep], "done": []}

    assert gitclaim.row_fr_depends_blocked_reason(blocked, doc) is None  # empty body = no stamp

    gitclaim.ensure_fr_queue_body(
        blocked,
        fetch_issue=lambda r, n: {"body": "Depends-on: #5\n"},
        cache=_fresh_cache(),
    )
    why = gitclaim.row_fr_depends_blocked_reason(blocked, doc)
    assert why and "depends-on open" in why
