# -*- coding: utf-8 -*-
"""FR #9832: applying hold to fr-digest clears offered/accepted Depends-on children."""
from __future__ import annotations

import sys
from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

REPO = "SimonBarnett/bobiverse"


def _row(num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": f"2026-11-24T10:00:{num % 60:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "event": "issues",
        "labels": [],
    }
    r.update(kw)
    return r


def test_fr9832_clear_offers_for_held_digest_children_unaccepted():
    digest = _row(
        9830,
        title="Digest: lessons",
        labels=["feature-request", "fr-digest", "digest", "hold"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9750,
        title="child",
        body="Depends-on: #9830\n",
        offered_to="flamingo-9976",
        offered_ts="2026-11-24T12:00:00Z",
        offered_via="offer",
    )
    other = _row(9999, body="Depends-on: (none)\n", offered_to="marchhare-1")
    doc = {"v": 1, "unaccepted": [digest, child, other], "accepted": [], "done": []}
    cleared = gitclaim.clear_offers_for_held_digest_children(None, doc, REPO, "9830")
    assert any("9750" in x for x in cleared)
    assert not child.get("offered_to")
    assert other.get("offered_to") == "marchhare-1"


def test_fr9832_clear_releases_accepted_child_only():
    child = _row(
        9750,
        body="Depends-on: #9830\n",
        nick="flamingo-9976",
        accepted_by="flamingo-9976",
        accepted_ts="2026-11-24T12:00:00Z",
    )
    other_acc = _row(
        8888,
        body="Depends-on: (none)\n",
        nick="flamingo-9976",
        accepted_by="flamingo-9976",
    )
    doc = {"v": 1, "unaccepted": [], "accepted": [child, other_acc], "done": []}
    cleared = gitclaim.clear_offers_for_held_digest_children(None, doc, REPO, "#9830")
    assert any("digest_hold_release_accepted" in x for x in cleared)
    acc_ids = {str(r.get("id")) for r in doc["accepted"]}
    assert "#8888" in acc_ids and "#9750" not in acc_ids
    retry = next(r for r in doc["unaccepted"] if r.get("id") == "#9750")
    assert not retry.get("offered_to") and not retry.get("nick")


def test_fr9832_label_hold_on_digest_clears_child_via_mutation(tmp_path):
    digest = _row(
        9744,
        title="Digest: dual Copilot",
        labels=["feature-request", "fr-digest", "digest"],
        body="Kind: fr-digest\n",
    )
    child = _row(
        9750,
        body="Depends-on: #9744\n",
        offered_to="flamingo-9976",
        offered_ts="2026-11-24T12:00:00Z",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [digest, child], "accepted": [], "done": [], "workers": {}},
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="#9744",
        event="issues",
        action="labeled",
        line="Digest: dual Copilot",
        title="Digest: dual Copilot",
        body="Kind: fr-digest\n",
        labels=("feature-request", "fr-digest", "digest", "hold"),
        state="open",
    )
    result = gitclaim.enqueue_unaccepted(tmp_path, claim)
    assert not str(result).startswith("error")
    doc = gitclaim.load_queue(tmp_path)
    child_row = next(r for r in doc["unaccepted"] if str(r.get("id")) == "#9750")
    assert not child_row.get("offered_to")
    notes = [n for n in (doc.get("stand_down") or []) if isinstance(n, dict)]
    assert any("FR #9832" in str(n.get("text") or "") for n in notes)


def test_fr9832_already_held_digest_label_noop_does_not_re_clear(tmp_path):
    digest = _row(
        9744,
        title="Digest: dual Copilot",
        labels=["feature-request", "fr-digest", "digest", "hold"],
        body="Kind: fr-digest\n",
    )
    child = _row(9750, body="Depends-on: #9744\n", offered_to="flamingo-9976")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [digest, child], "accepted": [], "done": [], "workers": {}},
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id="#9744",
        event="issues",
        action="labeled",
        line="Digest: dual Copilot",
        title="Digest: dual Copilot",
        body="Kind: fr-digest\n",
        labels=("feature-request", "fr-digest", "digest", "hold", "via-intake"),
        state="open",
    )
    gitclaim.enqueue_unaccepted(tmp_path, claim)
    doc = gitclaim.load_queue(tmp_path)
    child_row = next(r for r in doc["unaccepted"] if str(r.get("id")) == "#9750")
    assert child_row.get("offered_to") == "flamingo-9976"
