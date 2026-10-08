"""FR #2811: after GIVEUP/NACK, Jeeves offers that seat its next eligible job at once."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm
import shop_listen


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#marchhare", "#flamingo", "#win-mpre8vi4u6u"]
    )
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
            {
                "nick": nick,
                "state": "idle",
                "work": "",
                "updated": "2026-10-06T10:00:00Z",
            }
        ],
    }
    bobreport.save_digest(home, doc)


def _row(task="MRB", num=200, seq=1, **kw):
    r = {
        "repo": "SimonBarnett/bobiverse",
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-06T10:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/SimonBarnett/bobiverse/pull/{num}",
        "title": f"job {num}",
    }
    if task == "FR":
        r["url"] = f"https://github.com/SimonBarnett/bobiverse/issues/{num}"
    r.update(kw)
    return r


def _accepted(task="MRB", num=1, nick="marchhare-1", **kw):
    r = _row(task, num, 1, **kw)
    r["nick"] = nick
    r["accepted_ts"] = "2026-10-06T10:00:00Z"
    return r


def test_giveup_offers_immediate_alternative(home):
    """Fails on main before FR #2811: shop-listen returns ok with no assign push."""
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 2, 2)],
            "accepted": [_accepted("MRB", 1, nick)],
            "done": [],
        },
    )
    said = []
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP MRB SimonBarnett/bobiverse#1 self-MRB",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") and result.get("status") == "ok"
    # Helper used by irc_agent after shop-listen:
    n, job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1 and isinstance(job, dict)
    assert len(said) == 1
    assert said[0][0].lower() == channel
    assert said[0][1].startswith(f"{nick}: MRB SimonBarnett/bobiverse#2")
    doc = gitclaim.load_queue(home)
    alt = [r for r in doc["unaccepted"] if r["id"] == "#2"][0]
    assert "marchhare" in str(alt.get("offered_to") or "").lower()
    assert str(alt.get("offered_via") or "") == "giveup"
    given = [r for r in doc["unaccepted"] if r["id"] == "#1"][0]
    assert "marchhare" in str(given.get("giveup_seats") or "").lower()


def test_giveup_only_row_sends_nothing(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted("MRB", 1, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP MRB SimonBarnett/bobiverse#1",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0
    assert said == []
    given = gitclaim.load_queue(home)["unaccepted"][0]
    assert "marchhare" in str(given.get("giveup_seats") or "").lower()


def test_nack_offers_same_as_giveup(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 20, 2)],
            "accepted": [_accepted("FR", 10, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="NACK FR SimonBarnett/bobiverse#10",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1
    assert "bobiverse#20" in said[0][1].lower()


def test_self_mrb_alternative_excluded(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _row(
                    "MRB",
                    2,
                    2,
                    author_seat=nick,
                    implementer_seat=nick,
                )
            ],
            "accepted": [_accepted("MRB", 1, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP MRB SimonBarnett/bobiverse#1",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0
    assert said == []


def test_focus_respected_on_giveup_offer(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    fi.handle_unfocus_cmd(home, "all")
    fi.handle_focus_cmd(home, "strict on")
    fi.handle_focus_cmd(home, "SimonBarnett/not-this")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 20, 2)],
            "accepted": [_accepted("FR", 10, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP FR SimonBarnett/bobiverse#10",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0
    assert said == []


def test_needs_human_row_not_offered(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 20, 2, needs_human=True)],
            "accepted": [_accepted("FR", 10, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP FR SimonBarnett/bobiverse#10",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0
    assert said == []


def test_bored_rebroadcast_same_row_no_second_job(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 20, 2)],
            "accepted": [_accepted("FR", 10, nick)],
            "done": [],
        },
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP FR SimonBarnett/bobiverse#10",
        post_fn=lambda _p: 204,
    )
    said = []
    n, _job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append(t), now=1000.0
    )
    assert n == 1
    # FR #3192: seat already holds #20 from offer_after_giveup — no rebroadcast.
    st, job = gitclaim.offer_focus_top(home, nick, channel, now=1001.0)
    assert st == "empty" and job is None
    unas = gitclaim.load_queue(home)["unaccepted"]
    alts = [r for r in unas if r.get("id") == "#20"]
    assert len(alts) == 1
    assert alts[0].get("offered_to") == nick


def test_offer_via_giveup_extends_sticky_timeout(home):
    nick = "marchhare-1"
    channel = "#marchhare"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 20, 2)],
            "accepted": [],
            "done": [],
        },
    )
    said = []
    gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append(t), now=1000.0
    )
    row = gitclaim.load_queue(home)["unaccepted"][0]
    assert row.get("offered_via") == "giveup"
    # Within extended window (OFFER_TIMEOUT + GIVEUP_OFFER_EXTRA), other seat must not steal.
    _digest_idle(home, "flamingo-9")
    st, job = gitclaim.offer_focus_top(
        home, "flamingo-9", "#flamingo", now=1000.0 + gitclaim.OFFER_TIMEOUT_S + 30.0
    )
    assert st == "empty"
    assert job is None
