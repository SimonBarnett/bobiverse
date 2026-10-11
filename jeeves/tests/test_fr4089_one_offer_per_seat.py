# -*- coding: utf-8 -*-
"""FR #4089: one open offer/ACK per seat.

Acceptance:
- repeat DONE for a completed row (status=missing) sends no offer
- NACK from a nick that still holds another accepted row sends no giveup-offer
- done-offer + !bored within the sticky offer window send one offer, not two
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
                "updated": "2026-10-11T17:00:00Z",
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
        "ts": f"2026-10-11T17:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/SimonBarnett/bobiverse/pull/{num}",
        "title": f"job {num}",
    }
    if task == "FR":
        r["url"] = f"https://github.com/SimonBarnett/bobiverse/issues/{num}"
    r.update(kw)
    return r


def _accepted(task="MRB", num=1, nick="win-mpre8vi4u6u-1", **kw):
    seq = int(kw.pop("seq", 1))
    r = _row(task, num, seq, **kw)
    r["nick"] = nick
    r["accepted_ts"] = "2026-10-11T17:00:00Z"
    return r


def test_fr4089_repeat_done_missing_sends_no_offer(home):
    """DONE status=missing (ACC already in done[]) must not stamp a new offer."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    done_row = _accepted("FR", 4030, nick)
    done_row["done_ts"] = "2026-10-11T17:04:33Z"
    done_row["done_by"] = nick
    done_row["url"] = "https://github.com/SimonBarnett/bobiverse/pull/4082"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 4038, 2), _row("MRB", 4084, 3)],
            "accepted": [],
            "done": [done_row],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="DONE FR SimonBarnett/bobiverse#4030 https://github.com/SimonBarnett/bobiverse/pull/4082",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") and result.get("status") == "missing"
    # Chair wire: only status=ok triggers offer_after_done (FR #4089).
    from repo_layout import ROOT

    irc = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert 'verb == "DONE" and status == "ok"' in irc
    assert 'DONE" and status in ("ok", "missing")' not in irc
    # Defense in depth: seat that still holds another ACK gets zero done-offers.
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 4084, 3), _row("FR", 4090, 4)],
            "accepted": [_accepted("FR", 4038, nick)],
            "done": [done_row],
        },
    )
    said = []
    n, job = gitclaim.offer_after_done(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=2000.0
    )
    assert n == 0 and job is None
    assert said == []


def test_fr4089_nack_with_other_accepted_sends_no_giveup_offer(home):
    """NACK while another accepted row remains -> offer_after_giveup must not push."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 4085, 3)],
            "accepted": [
                _accepted("FR", 4038, nick),
                _accepted("MRB", 4084, nick, seq=2),
            ],
            "done": [],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="NACK MRB SimonBarnett/bobiverse#4084 holding FR #4038",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") and result.get("status") == "ok"
    # FR #4038 still accepted; giveup-offer must not fire a second assign.
    doc = gitclaim.load_queue(home)
    assert any(
        str(r.get("id")) == "#4038" and str(r.get("nick") or "") == nick
        for r in doc.get("accepted") or []
    )
    said = []
    n, job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0 and job is None
    assert said == []
    doc2 = gitclaim.load_queue(home)
    offered = [r for r in doc2["unaccepted"] if str(r.get("offered_to") or "")]
    assert offered == []


def test_fr4089_done_offer_plus_bored_within_window_one_offer(home):
    """done-offer then !bored inside sticky window -> one offer (bored nak-busy)."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 4038, 2), _row("MRB", 4084, 3)],
            "accepted": [_accepted("FR", 4030, nick)],
            "done": [],
        },
    )
    # Complete the accepted job, then done-offer the next.
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="DONE FR SimonBarnett/bobiverse#4030 https://github.com/SimonBarnett/bobiverse/pull/4082",
        post_fn=lambda _p: 204,
    )
    t0 = 1_000_000.0
    said = []
    n, job = gitclaim.offer_after_done(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=t0
    )
    assert n == 1 and isinstance(job, dict)
    assert len(said) == 1
    first_id = str(job.get("id") or "")
    assert first_id in ("#4038", "#4084")
    assert str(job.get("offered_via") or "") == "done"
    sticky = gitclaim.offer_timeout_s(job)
    assert sticky > gitclaim.OFFER_TIMEOUT_S

    # Past base OFFER_TIMEOUT_S but inside sticky via window: still pending.
    mid = t0 + gitclaim.OFFER_TIMEOUT_S + 30.0
    assert mid < t0 + sticky
    pending = gitclaim.seat_pending_offer(home, nick, mid)
    assert pending is not None
    assert str(pending.get("id") or "") == first_id
    gate = gitclaim.bored_gate(home, nick, channel, mid)
    assert gate == "busy"
    # Direct offer_focus_top must also refuse a second stamp.
    s2, j2 = gitclaim.offer_focus_top(home, nick, channel, now=mid)
    assert s2 == "empty" and j2 is None
    doc = gitclaim.load_queue(home)
    offered = [r for r in doc["unaccepted"] if str(r.get("offered_to") or "")]
    assert len(offered) == 1
    assert str(offered[0].get("id") or "") == first_id


def test_fr4089_seat_pending_uses_sticky_via_timeout(home):
    """Regression: seat_pending_offer must use offer_timeout_s, not bare OFFER_TIMEOUT_S."""
    nick = "marchhare-9"
    channel = "#marchhare"
    _digest_idle(home, nick)
    ts = datetime(2026, 10, 11, 17, 0, 0, tzinfo=timezone.utc)
    offered_ts = ts.isoformat().replace("+00:00", "Z")
    row = _row("FR", 10, 1, offered_to=nick, offered_ts=offered_ts, offered_via="done")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    now = (ts + timedelta(seconds=gitclaim.OFFER_TIMEOUT_S + 45)).timestamp()
    assert gitclaim.seat_pending_offer(home, nick, now) is not None
    # Ordinary (non-sticky) offer expires at OFFER_TIMEOUT_S.
    row2 = _row("FR", 11, 2, offered_to=nick, offered_ts=offered_ts)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row2], "accepted": [], "done": []},
    )
    assert gitclaim.seat_pending_offer(home, nick, now) is None
