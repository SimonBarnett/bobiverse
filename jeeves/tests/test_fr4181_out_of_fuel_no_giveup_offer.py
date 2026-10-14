"""FR #4181: GIVEUP reason=out-of-fuel must not giveup-offer that seat.

After an out-of-fuel GIVEUP, Jeeves marks the seat and skips the immediate
offer push. A later !bored (worker only posts that after fuel recovers)
clears the mark so the seat can be offered again. Other GIVEUP reasons keep
the FR #2811 giveup-offer behaviour.
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
                "updated": "2026-10-06T10:00:00Z",
            }
        ],
    }
    bobreport.save_digest(home, doc)


def _row(task="FR", num=200, seq=1, **kw):
    r = {
        "repo": "SimonBarnett/a-search",
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-12T02:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/SimonBarnett/a-search/issues/{num}",
        "title": f"job {num}",
    }
    if task == "MRB":
        r["url"] = f"https://github.com/SimonBarnett/a-search/pull/{num}"
    r.update(kw)
    return r


def _accepted(task="FR", num=1, nick="win-mpre8vi4u6u-11692", **kw):
    r = _row(task, num, 1, **kw)
    r["nick"] = nick
    r["accepted_ts"] = "2026-10-12T02:00:00Z"
    return r


def test_is_out_of_fuel_reason_matches_worker_wire():
    assert gitclaim.is_out_of_fuel_reason("out-of-fuel") is True
    assert gitclaim.is_out_of_fuel_reason("OUT-OF-FUEL") is True
    assert gitclaim.is_out_of_fuel_reason("out_of_fuel") is True
    assert gitclaim.is_out_of_fuel_reason("  out-of-fuel  ") is True
    assert gitclaim.is_out_of_fuel_reason("self-MRB") is False
    assert gitclaim.is_out_of_fuel_reason("require_machine=ionos") is False
    assert gitclaim.is_out_of_fuel_reason("") is False


def test_out_of_fuel_giveup_marks_seat_and_skips_offer(home):
    """Fails before FR #4181: offer_after_giveup would stamp the next row."""
    nick = "win-mpre8vi4u6u-11692"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("FR", 1183, 2)],
            "accepted": [_accepted("FR", 1176, nick)],
            "done": [],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP FR SimonBarnett/a-search#1176 out-of-fuel",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled") and result.get("status") == "ok"
    assert gitclaim.is_out_of_fuel_reason(str(result.get("reason") or ""))

    # Chair path: note the hold, then refuse the push (irc_agent does both).
    assert gitclaim.note_seat_out_of_fuel(home, nick) is True
    assert gitclaim.seat_is_out_of_fuel(home, nick) is True

    said = []
    n, job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 0 and job is None
    assert said == []
    doc = gitclaim.load_queue(home)
    assert not any(r.get("offered_to") for r in doc["unaccepted"])
    # Job returned to unaccepted for a fuelled seat.
    assert any(r.get("id") == "#1176" for r in doc["unaccepted"])


def test_other_giveup_reason_still_offers(home):
    nick = "win-mpre8vi4u6u-11692"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 1538, 2)],
            "accepted": [_accepted("MRB", 1500, nick)],
            "done": [],
        },
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel=channel,
        body="GIVEUP MRB SimonBarnett/a-search#1500 self-MRB",
        post_fn=lambda _p: 204,
    )
    assert result.get("status") == "ok"
    assert not gitclaim.is_out_of_fuel_reason(str(result.get("reason") or ""))
    assert not gitclaim.seat_is_out_of_fuel(home, nick)

    said = []
    n, job = gitclaim.offer_after_giveup(
        home, nick, channel, say=lambda ch, t: said.append((ch, t)), now=1000.0
    )
    assert n == 1 and isinstance(job, dict)
    assert job["id"] == "#1538"
    assert len(said) == 1


def test_bored_after_clear_offers_again(home):
    """Worker !bored after fuel returns clears the chair mark and can be offered."""
    nick = "win-mpre8vi4u6u-13252"
    channel = "#win-mpre8vi4u6u"
    _digest_idle(home, nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_row("MRB", 1538, 1)],
            "accepted": [],
            "done": [],
        },
    )
    assert gitclaim.note_seat_out_of_fuel(home, nick)
    assert gitclaim.bored_gate(home, nick, channel, 2000.0) == "busy"
    assert gitclaim.offer_focus_top(home, nick, channel, now=2000.0)[0] != "ok"

    cleared = gitclaim.clear_seat_out_of_fuel(home, nick)
    assert cleared is True
    assert not gitclaim.seat_is_out_of_fuel(home, nick)
    assert gitclaim.bored_gate(home, nick, channel, 2100.0) == "ok"
    st, job = gitclaim.offer_focus_top(home, nick, channel, now=2100.0)
    assert st == "ok" and job["id"] == "#1538"


def test_irc_agent_skips_giveup_offer_on_out_of_fuel_reason():
    """Source pin: shop GIVEUP out-of-fuel notes the seat and skips offer_after_giveup."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[2]
    text = (root / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "is_out_of_fuel_reason" in text
    assert "note_seat_out_of_fuel" in text
    assert "giveup-offer skipped" in text
    assert "clear_seat_out_of_fuel" in text
