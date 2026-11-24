# -*- coding: utf-8 -*-
"""FR #9558: drop seat-hold when ACC moves to a different nick.

#9403 / PR #9547 clears holds on offer-timeout. This covers ACC moved: offer A,
timeout (or clear pin), ACC B → A's hold must be gone so !assign A can take other work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"
NICK_A = "flamingo-17068"
NICK_B = "redqueen-668"


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fr9558_accept_clears_other_nicks_hold(tmp_path: Path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    now = 1_700_000_000.0
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#9526",
        "title": "host heal",
        "offered_to": NICK_B,
        "offered_ts": _iso(now),
        "offered_channel": "#redqueen",
        "line": f"FR {REPO}#9526",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    # Orphan offer hold for A while B is the current offered_to.
    gitclaim.note_seat_hold(
        home, NICK_A, {"repo": REPO, "task": "FR", "id": "#9526"}, via="offer"
    )
    assert gitclaim._seat_key(NICK_A) in gitclaim._load_seat_holds_unlocked(home)

    st, job = gitclaim.accept_offered(home, NICK_B, "#redqueen")
    assert st == "ok"
    assert job and job.get("id") == "#9526"

    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(NICK_A) not in holds
    # Acceptor is busy via accepted[], not via a leftover offer hold.
    assert gitclaim._seat_key(NICK_B) not in holds
    assert gitclaim.seat_open_job(home, NICK_A, now) == ""
    busy_b = gitclaim.seat_open_job(home, NICK_B, now)
    assert "9526" in busy_b or "FR" in busy_b


def test_fr9558_purge_orphan_hold_when_acc_other_nick(tmp_path: Path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    now = 1_700_000_000.0
    accepted = {
        "repo": REPO,
        "task": "FR",
        "id": "#9526",
        "nick": NICK_B,
        "accepted_ts": _iso(now),
        "line": f"FR {REPO}#9526",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [accepted], "done": []},
    )
    gitclaim.note_seat_hold(
        home, NICK_A, {"repo": REPO, "task": "FR", "id": "#9526"}, via="offer"
    )
    assert gitclaim._seat_key(NICK_A) in gitclaim._load_seat_holds_unlocked(home)

    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda *_a, **_k: {NICK_A, NICK_B})
    n = gitclaim.purge_orphan_seat_holds(home, now=now)
    assert n >= 1
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(NICK_A) not in holds
    assert gitclaim.seat_open_job(home, NICK_A, now) == ""


def test_fr9558_note_hold_clears_other_nicks_for_same_job(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    job = {"repo": REPO, "task": "FR", "id": "#9526"}
    gitclaim.note_seat_hold(home, NICK_A, job, via="offer")
    gitclaim.note_seat_hold(home, NICK_B, job, via="offer")
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(NICK_A) not in holds
    assert gitclaim._seat_key(NICK_B) in holds
