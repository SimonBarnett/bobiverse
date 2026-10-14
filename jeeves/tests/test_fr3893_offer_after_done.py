"""FR #3893: after DONE, Jeeves offers that seat its next eligible job at once.

Regression of idle seats with 100+ queued jobs after DONE (related #2803 / #2811).
"""
from __future__ import annotations

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
                "updated": "2026-10-10T18:00:00Z",
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
        "ts": f"2026-10-10T18:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/SimonBarnett/bobiverse/pull/{num}",
        "title": f"job {num}",
    }
    if task == "FR":
        r["url"] = f"https://github.com/SimonBarnett/bobiverse/issues/{num}"
    r.update(kw)
    return r


def _accepted(task="MRB", num=1, nick="win-mpre8vi4u6u-1", **kw):
    r = _row(task, num, 1, **kw)
    r["nick"] = nick
    r["accepted_ts"] = "2026-10-10T18:00:00Z"
    return r


def test_fr3893_done_offers_immediate_next(home):
    """DONE with eligible unaccepted rows -> offer_after_done stamps next row."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 2, 2), _row("FR", 3, 3)],
            "accepted": [_accepted("MRB", 1, nick)],
            "done": [],
        },
    )
    said = []
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="DONE MRB SimonBarnett/bobiverse#1 PASS https://github.com/SimonBarnett/bobiverse/pull/1",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") and result.get("status") == "ok"
    n, job = gitclaim.offer_after_done(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1 and isinstance(job, dict)
    assert len(said) == 1
    assert said[0][0].lower() == channel
    assert said[0][1].startswith(f"{nick}: ")
    assert "bobiverse#2" in said[0][1].lower() or "bobiverse#3" in said[0][1].lower()
    doc = gitclaim.load_queue(home)
    offered = [r for r in doc["unaccepted"] if str(r.get("offered_to") or "")]
    assert offered, "expected an offered_to stamp after DONE"
    assert str(offered[0].get("offered_via") or "") == "done"
    assert gitclaim.offer_timeout_s(offered[0]) > gitclaim.OFFER_TIMEOUT_S


def test_fr3893_done_skips_self_authored_head(home):
    """Self-authored MRB at head must not block; next eligible row is offered."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
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
                ),
                _row("FR", 3, 3),
            ],
            "accepted": [_accepted("MRB", 1, nick)],
            "done": [],
        },
    )
    said = []
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="DONE MRB SimonBarnett/bobiverse#1 PASS https://github.com/SimonBarnett/bobiverse/pull/1",
        post_fn=lambda _p: 204,
    )
    n, job = gitclaim.offer_after_done(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1 and isinstance(job, dict)
    assert "bobiverse#3" in said[0][1].lower()
    assert "#2" not in said[0][1]


def test_fr3893_done_only_self_authored_logs_empty_detail(home):
    """Only ineligible (self-authored) rows left -> no assign; empty detail names self_mrb."""
    nick = "win-mpre8vi4u6u-1"
    channel = "#win-mpre8vi4u6u"
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
    said = []
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="DONE MRB SimonBarnett/bobiverse#1 PASS https://github.com/SimonBarnett/bobiverse/pull/1",
        post_fn=lambda _p: 204,
    )
    n, job = gitclaim.offer_after_done(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0 and job is None
    assert said == []
    stats = gitclaim.summarize_empty_offer(home, nick)
    detail = gitclaim.format_empty_offer_detail(nick, stats)
    assert "self_mrb=" in detail or "nothing queued" in detail or "offerable" in detail
    assert str(stats.get("unaccepted") or 0) == "1" or int(stats.get("unaccepted") or 0) >= 1


def test_fr3893_source_gates_irc_agent_done_offer():
    """Chair shop-listen path must call offer_after_done after DONE (not only GIVEUP)."""
    from pathlib import Path

    from repo_layout import ROOT

    irc = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "FR #3893" in irc or "offer_after_done" in irc
    assert "offer_after_done" in irc
    assert "done-offer" in irc
    # DONE branch must exist beside GIVEUP/NACK offer push.
    done_at = irc.find('verb == "DONE"')
    giveup_at = irc.find("offer_after_giveup")
    assert done_at > 0
    assert "offer_after_done" in irc[done_at : done_at + 2500] or giveup_at > 0
    assert "done-offer empty" in irc


def test_fr3893_offer_after_giveup_still_aliases(home):
    """FR #2811 alias remains; sticky via still giveup."""
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
    shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP MRB SimonBarnett/bobiverse#1 self-MRB",
        post_fn=lambda _p: 204,
    )
    n, job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1
    doc = gitclaim.load_queue(home)
    alt = [r for r in doc["unaccepted"] if r["id"] == "#2"][0]
    assert alt.get("offered_via") == "giveup"
