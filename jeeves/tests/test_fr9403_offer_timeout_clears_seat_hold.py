"""FR #9403: offer-timeout must clear seat-holds (not leave idle seat busy held).

Monitor 2026-11-24: flamingo-17068 offer-timeout:idle-no-ack left seat-holds.json
pin while digest idle and ACC moved — !assign refused busy (held FR …).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"
NICK = "flamingo-17068"


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fr9403_purge_stale_pin_clears_seat_hold_for_aged_live(tmp_path: Path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    now = 1_700_000_000.0
    timeout = float(gitclaim.offer_timeout_s({}))
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#9526",
        "title": "host heal",
        "body": "Depends-on: (none)\n",
        "labels": [],
        "offered_to": NICK,
        "offered_ts": _iso(now - timeout - 5.0),
        "line": f"FR {REPO}#9526",
    }
    doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.note_seat_hold(
        home,
        NICK,
        {"repo": REPO, "task": "FR", "id": "#9526"},
        via="offer",
    )
    assert gitclaim._seat_key(NICK) in gitclaim._load_seat_holds_unlocked(home)

    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda *_a, **_k: {NICK})
    monkeypatch.setattr(
        gitclaim, "seat_submit_verify_in_flight", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        gitclaim, "offer_timeout_reason", lambda *_a, **_k: "offer-timeout:idle-no-ack"
    )

    n = gitclaim.purge_stale_offered_pins(home, now=now)
    assert n >= 1
    q = gitclaim.load_queue(home)
    assert all(not str(r.get("offered_to") or "") for r in q.get("unaccepted") or [])
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(NICK) not in holds
    assert gitclaim.seat_open_job(home, NICK, now) == ""
