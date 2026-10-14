# -*- coding: utf-8 -*-
"""FR #4089: one open job per seat.

A seat that holds an accepted (not-yet-DONE) row, any offer pinned to it (no age
window) or a remembered offer in seat-holds.json is never offered or pushed a second
job — not on !bored, not after DONE (incl. repeat / status=missing DONE), not after
NACK/GIVEUP. Rows still time back to the queue for *other* seats.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
ME = "marchhare-35600"
OTHER = "marchhare-35601"
SHOP = "#marchhare"
ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "common" / "scripts" / "irc_agent.py"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    # FR #4211: live_seat_nicks prefers worker_list; bare legacy workers without a
    # heartbeat are ghosts (empty live set), which would break hold-void checks.
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-10-14T20:00:00Z"},
        {"nick": OTHER, "state": "idle", "work": "", "updated": "2026-10-14T20:00:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, [])
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row(task: str, num: int, seq: int | None = None, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "seq": seq if seq is not None else num,
        "ts": "2026-10-11T10:00:00Z",
        "line": f"{task} {REPO}#{num}",
        "url": f"https://github.com/{REPO}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _queue(home: Path, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": unaccepted, "accepted": accepted or [], "done": [], "workers": {}},
    )


def _accepted(task: str, num: int, nick: str = ME) -> dict:
    r = _row(task, num)
    r["nick"] = nick
    r["accepted_ts"] = _ts(30)
    return r


def _say_sink():
    sent: list[tuple[str, str]] = []

    def say(ch, text):
        sent.append((ch, text))
        return True

    return sent, say


# --- accepted job blocks every offer path -----------------------------------------

def test_accepted_job_blocks_bored(home: Path):
    _queue(home, [_row("FR", 10), _row("FR", 11)], [_accepted("FR", 1)])
    gate = gitclaim.bored_gate(home, ME, SHOP, time.time(), session_started=0.0)
    assert gate == "busy"


def test_stale_accepted_job_still_reaped_on_bored(home: Path):
    """Safety valve: the existing BUSY_STALE_S reaper still frees a seat whose ACK is old."""
    old = _accepted("FR", 1)
    old["accepted_ts"] = _ts(gitclaim.BUSY_STALE_S + 60)
    _queue(home, [_row("FR", 10)], [old])
    assert gitclaim.bored_gate(home, ME, SHOP, time.time()) == "ok"
    st, job = gitclaim.offer_focus_top(home, ME, SHOP)
    assert st == "ok" and job["id"] == "#10"
    st, job = gitclaim.offer_focus_top(home, ME, SHOP)
    assert st == "empty" and job is None


def test_accepted_job_blocks_done_push(home: Path):
    """DONE for some other / already-completed job (status=missing class) never pushes."""
    _queue(home, [_row("FR", 10)], [_accepted("FR", 1)])
    sent, say = _say_sink()
    n, job = gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert (n, job) == (0, None) and sent == []


def test_accepted_job_blocks_nack_push(home: Path):
    _queue(home, [_row("FR", 10)], [_accepted("FR", 1)])
    sent, say = _say_sink()
    n, job = gitclaim.offer_after_giveup(home, ME, SHOP, say=say)
    assert (n, job) == (0, None) and sent == []


def test_accepted_job_blocks_assign_row(home: Path):
    _queue(home, [_row("FR", 10)], [_accepted("FR", 1)])
    st, why = gitclaim.assign_row(home, ME, REPO, "FR", "#10")
    assert st == "refused" and "busy" in str(why)


# --- free seat still gets an offer right after DONE --------------------------------

def test_free_seat_gets_one_offer_after_done(home: Path):
    _queue(home, [_row("FR", 10), _row("FR", 11)])
    sent, say = _say_sink()
    n, job = gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert n == 1 and job["id"] == "#10"
    assert len(sent) == 1 and "#10" in sent[0][1]
    # A second DONE (repeat) or !bored right after must not give a second job.
    n2, job2 = gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert (n2, job2) == (0, None)
    st, _ = gitclaim.offer_focus_top(home, ME, SHOP)
    assert st == "empty"
    assert len(sent) == 1
    hold = gitclaim._load_seat_holds_unlocked(home).get(ME)
    assert hold and hold["id"] == "#10"


# --- the old-offer case (window expired, seat still holding the assign) -------------

def test_old_offer_still_blocks_seat_but_frees_row_for_others(home: Path):
    """Offer made 10 min ago (> 180 s push window) and never ACKed: the seat is still
    blocked; the row times back to the queue for another seat as before."""
    _queue(home, [_row("FR", 10), _row("FR", 11)])
    sent, say = _say_sink()
    n, job = gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert n == 1 and job["id"] == "#10"
    # Age the pin and the hold by 10 minutes.
    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        for r in doc["unaccepted"]:
            if r.get("offered_to"):
                r["offered_ts"] = _ts(600)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        holds = gitclaim._load_seat_holds_unlocked(home)
        holds[ME]["ts"] = _ts(600)
        gitclaim._save_seat_holds_unlocked(home, holds)
    assert gitclaim.seat_pending_offer(home, ME) is None  # row window expired
    assert gitclaim.seat_open_job(home, ME).startswith(("offered", "held"))
    now = time.time() + 1
    assert gitclaim.bored_gate(home, ME, SHOP, now + 10_000) == "busy"
    assert gitclaim.offer_after_done(home, ME, SHOP, say=say) == (0, None)
    assert gitclaim.offer_after_giveup(home, ME, SHOP, say=say) == (0, None)
    st, _ = gitclaim.offer_focus_top(home, ME, SHOP)
    assert st == "empty"
    # The other seat can take the expired row.
    st2, job2 = gitclaim.offer_focus_top(home, OTHER, SHOP)
    assert st2 == "ok" and job2["id"] == "#10"
    # FR #4260: re-offer to OTHER clears ME's hold for that job so ME is not stuck
    # busy (held ...) forever; ME can take the next queued row (#11).
    assert gitclaim.seat_open_job(home, ME) == ""
    st3, job3 = gitclaim.offer_focus_top(home, ME, SHOP)
    assert st3 == "ok" and job3["id"] == "#11"
    assert len(sent) == 1


# --- what clears an open job ------------------------------------------------------

def test_nack_of_offer_clears_hold_and_pin(home: Path):
    _queue(home, [_row("FR", 10), _row("FR", 11)])
    sent, say = _say_sink()
    gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert gitclaim.seat_open_job(home, ME)
    assert gitclaim.clear_seat_hold(home, ME, repo=REPO, task="FR", ident="#10", clear_pins=True)
    assert gitclaim.seat_open_job(home, ME) == ""
    assert not any(r.get("offered_to") for r in gitclaim.load_unaccepted(home))


def test_hold_for_other_job_not_cleared_by_unrelated_done(home: Path):
    _queue(home, [_row("FR", 10)])
    sent, say = _say_sink()
    gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert not gitclaim.clear_seat_hold(home, ME, repo=REPO, task="FR", ident="#99", clear_pins=True)
    assert gitclaim.seat_open_job(home, ME)


def test_quit_clears_everything_for_nick(home: Path):
    _queue(home, [_row("FR", 10)])
    sent, say = _say_sink()
    gitclaim.offer_after_done(home, ME, SHOP, say=say)
    assert gitclaim.clear_seat_hold(home, ME, clear_pins=True)
    assert gitclaim.seat_open_job(home, ME) == ""


def test_hold_reaped_after_max_age(home: Path):
    gitclaim._save_seat_holds_unlocked(
        home,
        {ME.lower(): {"nick": ME, "repo": REPO, "task": "FR", "id": "#5",
                      "ts": _ts(gitclaim.SEAT_HOLD_MAX_S + 5)}},
    )
    assert gitclaim.seat_open_job(home, ME) == ""


def test_hold_void_when_seat_left_live_list(home: Path):
    gone = "marchhare-11111"
    gitclaim._save_seat_holds_unlocked(
        home,
        {gone: {"nick": gone, "repo": REPO, "task": "FR", "id": "#5", "ts": _ts(30)}},
    )
    assert gitclaim.seat_open_job(home, gone) == ""


def test_undelivered_push_does_not_block_seat(home: Path):
    _queue(home, [_row("FR", 10)])
    n, job = gitclaim.offer_after_done(home, ME, SHOP, say=lambda ch, t: False)
    assert (n, job) == (0, None)
    assert gitclaim.seat_open_job(home, ME) == ""


def test_seat_pending_offer_uses_per_row_window(home: Path):
    """Item 3: done/giveup pushed offers stay pending for the full 180 s, not a flat 90 s."""
    _queue(home, [_row("FR", 10, offered_to=ME, offered_ts=_ts(120), offered_via="done")])
    assert gitclaim.seat_pending_offer(home, ME) is not None
    _queue(home, [_row("FR", 10, offered_to=ME, offered_ts=_ts(120))])
    assert gitclaim.seat_pending_offer(home, ME) is None


def test_holds_file_is_separate_from_queue(home: Path):
    _queue(home, [_row("FR", 10)])
    sent, say = _say_sink()
    gitclaim.offer_after_done(home, ME, SHOP, say=say)
    q = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    assert set(q) >= {"unaccepted", "accepted", "done"}
    assert gitclaim._seat_holds_path(home).name == "seat-holds.json"


# --- irc_agent wiring (source pins) -----------------------------------------------

def test_irc_agent_done_push_only_on_status_ok():
    src = IRC.read_text(encoding="utf-8")
    assert 'verb == "DONE" and status in ("ok", "missing")' not in src
    i = src.find('elif verb == "DONE" and status == "ok":')
    assert i > 0 and "offer_after_done" in src[i : i + 600]
    assert "done-offer skipped" in src


def test_irc_agent_clears_hold_on_answer_and_quit():
    src = IRC.read_text(encoding="utf-8")
    assert src.count("gitclaim.clear_seat_hold(") >= 3
    assert "reason=quit" in src and "reason=part" in src
