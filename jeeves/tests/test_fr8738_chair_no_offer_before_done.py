"""FR #8738: chair side of "no next job before the prior ACK has settled".

The chair keeps FR #3192: no new ``offered_to`` for nick N while N's accepted row is
listed. Only once DONE/NACK/GIVEUP for that row is processed may one next job be
stamped (FR #3893 done-offer / FR #2811 giveup-offer). A later ``!bored`` from the
same seat (for example the worker's done-miss ``!bored`` after
``GIVEUP ... no-terminal-reply``) must not stamp a second job while that offer is out.

The worker side (bob/tests/test_fr8738_closing_turn_hold.py) keeps the pushed offer
parked until the turn that closed the prior job has ended.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm
import shop_listen

NICK = "marchhare-12400"
SHOP = "#marchhare"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#flamingo"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "bobiverse")
    return tmp_path


def _digest_idle(home: Path, nick: str) -> None:
    mid = bobreport.parse_seat_nick(nick)[0]
    doc = bobreport.load_digest(home)
    machines = doc.setdefault("machines", {})
    machines[mid] = {
        "id": mid,
        "online": True,
        "working_on": "",
        "worker_list": [
            {"nick": nick, "state": "idle", "work": "", "updated": "2026-11-21T17:00:00Z"}
        ],
    }
    bobreport.save_digest(home, doc)


def _row(task: str, num: int, seq: int) -> dict:
    url = (
        f"https://github.com/SimonBarnett/bobiverse/pull/{num}"
        if task == "MRB"
        else f"https://github.com/SimonBarnett/bobiverse/issues/{num}"
    )
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-21T17:00:{seq:02d}Z",
        "line": "x",
        "url": url,
        "title": f"job {num}",
    }


def _queue_with_accepted(home: Path, accepted_ts: str) -> None:
    acc = _row("MRB", 8672, 1)
    acc["nick"] = NICK
    acc["accepted_ts"] = accepted_ts
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 8673, 2), _row("FR", 8674, 3)],
            "accepted": [acc],
            "done": [],
        },
    )


def _offered(home: Path) -> list[dict]:
    doc = gitclaim.load_queue(home)
    return [r for r in doc["unaccepted"] if str(r.get("offered_to") or "")]


def _now_iso(now: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))


def test_fr8738_no_offer_while_accepted_row_open(home):
    now = time.time()
    _digest_idle(home, NICK)
    _queue_with_accepted(home, _now_iso(now - 60))
    said: list = []
    assert gitclaim.bored_gate(home, NICK, SHOP, now) == "busy"
    n, job = gitclaim.offer_after_done(
        home, NICK, SHOP, say=lambda ch, t: said.append((ch, t)), now=now
    )
    assert (n, job) == (0, None)
    assert said == []
    assert _offered(home) == []


def test_fr8738_done_then_one_offer_and_bored_does_not_stamp_second(home):
    now = time.time()
    _digest_idle(home, NICK)
    _queue_with_accepted(home, _now_iso(now - 60))
    res = shop_listen.handle_shop_worker_line(
        home,
        nick=NICK,
        channel=SHOP,
        body=(
            "DONE MRB SimonBarnett/bobiverse#8672 PASS "
            "https://github.com/SimonBarnett/bobiverse/pull/8672"
        ),
        post_fn=lambda _p: 204,
    )
    assert res.get("handled") and res.get("status") == "ok"
    said: list = []
    n, job = gitclaim.offer_after_done(
        home, NICK, SHOP, say=lambda ch, t: said.append((ch, t)), now=now
    )
    assert n == 1 and isinstance(job, dict)
    assert len(said) == 1
    first = _offered(home)
    assert len(first) == 1 and first[0]["offered_to"] == NICK
    # The seat's next !bored (before it ACKs the pushed offer) is busy: no second stamp.
    assert gitclaim.bored_gate(home, NICK, SHOP, now + 5) == "busy"
    n2, job2 = gitclaim.offer_after_done(
        home, NICK, SHOP, say=lambda ch, t: said.append((ch, t)), now=now + 5
    )
    assert (n2, job2) == (0, None)
    assert len(said) == 1
    assert len(_offered(home)) == 1


def test_fr8738_done_miss_giveup_bored_does_not_stamp_second_job(home):
    """Worker done-miss release: GIVEUP no-terminal-reply then !bored (FR #4784)."""
    now = time.time()
    _digest_idle(home, NICK)
    _queue_with_accepted(home, _now_iso(now - 600))
    res = shop_listen.handle_shop_worker_line(
        home,
        nick=NICK,
        channel=SHOP,
        body="GIVEUP MRB SimonBarnett/bobiverse#8672 no-terminal-reply",
        post_fn=lambda _p: 204,
    )
    assert res.get("handled")
    said: list = []
    n, _job = gitclaim.offer_after_giveup(
        home, NICK, SHOP, say=lambda ch, t: said.append((ch, t)), now=now
    )
    stamped = _offered(home)
    assert n <= 1 and len(stamped) <= 1
    # The done-miss !bored that follows the GIVEUP: never a second job for this seat.
    gate = gitclaim.bored_gate(home, NICK, SHOP, now + 1)
    if stamped:
        assert gate == "busy"
    st, j2 = gitclaim.offer_focus_top(home, NICK, SHOP, now=now + 1)
    mine = [r for r in _offered(home) if r.get("offered_to") == NICK]
    assert len(mine) <= 1, mine
    if stamped:
        assert st != "ok" or (j2 and j2["id"] == stamped[0]["id"])
