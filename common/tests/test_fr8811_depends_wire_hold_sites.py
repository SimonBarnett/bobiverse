"""FR #8811 / BOB-D7: Depends gate wired beside every FR hold offer site."""
from __future__ import annotations

import re
from pathlib import Path

import gitclaim as gc

GITCLAIM = Path(__file__).resolve().parents[1] / "scripts" / "gitclaim.py"


def test_bob_d7_wire_hold_marker_and_helper():
    src = GITCLAIM.read_text(encoding="utf-8")
    assert "bob_d7_wire_hold" in src
    assert callable(gc.row_fr_depends_blocked_reason)


def test_depends_blocked_when_depend_still_in_queue():
    doc = {
        "unaccepted": [
            {
                "task": "FR",
                "id": "#42",
                "title": "other",
                "repo": "SimonBarnett/foo",
                "body": "",
            }
        ],
        "accepted": [],
    }
    row = {
        "task": "FR",
        "id": "#99",
        "repo": "SimonBarnett/foo",
        "title": "child",
        "body": "Depends-on: #42\n",
    }
    why = gc.row_fr_depends_blocked_reason(row, doc)
    assert why is not None
    assert "depends-on open" in why
    assert "#42" in why


def test_depends_clear_when_no_open_depend():
    doc = {"unaccepted": [], "accepted": []}
    row = {
        "task": "FR",
        "id": "#99",
        "repo": "SimonBarnett/foo",
        "title": "child",
        "body": "Depends-on: #42\n",
    }
    assert gc.row_fr_depends_blocked_reason(row, doc) is None


def _call_sites(src: str, name: str) -> list[int]:
    lines = src.splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        if re.search(rf"\b{name}\s*\(", line) and not re.match(
            rf"^\s*def\s+{name}\s*\(", line
        ):
            out.append(i)
    return out


def test_s1_every_fr_hold_call_site_has_depends_gate_nearby():
    """Fail-when: hold sites miss depends check."""
    src = GITCLAIM.read_text(encoding="utf-8")
    hold_sites = _call_sites(src, "row_fr_hold_reason") + _call_sites(
        src, "fr_hold_reason"
    )
    lines = src.splitlines()
    hold_sites = [
        n
        for n in hold_sites
        if "return fr_hold_reason" not in lines[n - 1]
    ]
    # Enqueue-time hold skip keeps Depends-on rows queueable (FR #8754); depends
    # gate is offer/purge/reconcile-time. Exclude _append_unaccepted hold site.
    hold_sites = [
        n
        for n in hold_sites
        if "never enqueue FR for issues on hold" not in "\n".join(lines[max(0, n - 8) : n])
    ]
    assert hold_sites, "expected FR hold call sites in gitclaim"

    depends_sites = set(_call_sites(src, "row_fr_depends_blocked_reason"))
    assert depends_sites, "expected Depends gate call sites"

    window = 18
    missing = []
    for hn in hold_sites:
        nearby = range(hn, min(len(lines), hn + window) + 1)
        if not any(d in nearby for d in depends_sites):
            missing.append((hn, lines[hn - 1].strip()[:100]))
    assert missing == [], f"hold sites missing nearby depends gate: {missing}"
