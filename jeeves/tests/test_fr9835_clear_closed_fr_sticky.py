# -*- coding: utf-8 -*-
"""FR #9835: stamped CLOSED FR sticky offered_to / seat-holds must not busy a seat."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import gitclaim
import registered_machines

NICK = "flamingo-7124"
OTHER = "redqueen-6400"
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-25T12:00:00Z"},
    ]
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": OTHER, "state": "idle", "work": "", "updated": "2026-11-25T12:00:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _closed_offered_row(**extra) -> dict:
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#9685",
        "title": "phantom CLOSED sticky",
        "labels": ["feature-request", "via-intake"],
        "body": "phantom class of #9685\n",
        "line": f"FR {REPO}#9685",
        "url": f"https://github.com/{REPO}/issues/9685",
        "state": "closed",
        "offered_to": NICK,
        "offered_ts": _ts(30),  # within offer timeout
        "offered_channel": "#flamingo",
        "offered_via": "offer",
        "seq": 1,
    }
    row.update(extra)
    return row


def test_fr9835_clear_closed_fr_sticky_offers_drops_row():
    doc = {"unaccepted": [_closed_offered_row()], "accepted": [], "done": []}
    dropped = gitclaim.clear_closed_fr_sticky_offers(doc)
    assert dropped
    assert "closed_fr_clear_sticky" in dropped[0]
    assert doc["unaccepted"] == []


def test_fr9835_open_fr_sticky_kept():
    row = _closed_offered_row(state="open")
    doc = {"unaccepted": [row], "accepted": [], "done": []}
    dropped = gitclaim.clear_closed_fr_sticky_offers(doc)
    assert dropped == []
    assert len(doc["unaccepted"]) == 1
    assert doc["unaccepted"][0].get("offered_to") == NICK


def test_fr9835_seat_not_busy_within_offer_timeout(tmp_path: Path, monkeypatch):
    """Fail-when: closed sticky FR kept seat busy (offered ...) inside OFFER_TIMEOUT_S."""
    home = _home(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).timestamp()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_closed_offered_row()],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    assert gitclaim.seat_open_job(home, NICK, now=now) == ""
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("id") or "").endswith("9685") for r in q.get("unaccepted") or []
    )


def test_fr9835_clears_via_offer_hold_with_closed_row(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).timestamp()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_closed_offered_row()],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    assert gitclaim.note_seat_hold(
        home,
        NICK,
        {"repo": REPO, "task": "FR", "id": "#9685", "offered_ts": _ts(30)},
        via="offer",
    )
    assert gitclaim.seat_open_job(home, NICK, now=now) == ""
    holds = gitclaim._load_seat_holds_unlocked(home, now)
    key = gitclaim._seat_key(NICK)
    assert key not in holds or not isinstance(holds.get(key), dict)


def test_fr9835_purge_closed_fr_clears_holds(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).timestamp()
    doc = {
        "unaccepted": [_closed_offered_row()],
        "accepted": [],
        "done": [],
    }
    assert gitclaim.note_seat_hold(
        home,
        NICK,
        {"repo": REPO, "task": "FR", "id": "#9685", "offered_ts": _ts(20)},
        via="offer",
    )
    n = gitclaim._purge_closed_fr_unaccepted(doc, home=home)
    assert n == 1
    assert doc["unaccepted"] == []
    holds = gitclaim._load_seat_holds_unlocked(home, now)
    key = gitclaim._seat_key(NICK)
    assert key not in holds or not isinstance(holds.get(key), dict)


def test_fr9835_assign_tip_mrb_succeeds_after_closed_sticky(tmp_path: Path, monkeypatch):
    """Closed FR sticky ⇒ !assign tip MRB succeeds (acceptance from issue)."""
    home = _home(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc).timestamp()
    mrb = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9910",
        "title": "tip MRB",
        "line": f"MRB {REPO}#9910",
        "url": f"https://github.com/{REPO}/pull/9910",
        "seq": 2,
        "state": "open",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_closed_offered_row(), mrb],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}, OTHER: {"last_seen": 9e12}},
        },
    )
    assert gitclaim.note_seat_hold(
        home,
        NICK,
        {"repo": REPO, "task": "FR", "id": "#9685", "offered_ts": _ts(25)},
        via="offer",
    )
    # Seat must be free so !assign / offer can proceed.
    assert gitclaim.seat_open_job(home, NICK, now=now) == ""
    st, job = gitclaim.offer_focus_top(home, OTHER, "#redqueen", now=now)
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "MRB"
    assert str(job.get("id") or "").endswith("9910")
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("id") or "").endswith("9685") for r in q.get("unaccepted") or []
    )
