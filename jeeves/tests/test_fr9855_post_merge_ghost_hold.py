# -*- coding: utf-8 -*-
"""FR #9855: stuck-sweep clears post-merge / idle-report ghost via=offer holds."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import stuck_job_sweep as sjs
import pytest

REPO = "SimonBarnett/bobiverse"
ME = "redqueen-12648"
OTHER = "flamingo-16952"
SHOP = "#redqueen"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen", "walrus"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    # Digest paints idle + empty working_on while chair may still hold busy.
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": ME,
            "state": "idle",
            "work": "",
            "working_on": "",
            "updated": "2026-11-25T00:30:00Z",
        },
    ]
    # No sibling idle seats in digest — idle-offer push must not steal the tip.
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = []
    bobreport.save_digest(tmp_path, digest)
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _queue(home: Path, *, unaccepted=None, accepted=None, done=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
            "workers": {ME: {"last_seen": 9e12}, OTHER: {"last_seen": 9e12}},
        },
    )


def _tip_mrb() -> dict:
    return {
        "repo": REPO,
        "task": "MRB",
        "id": "#9842",
        "seq": 2,
        "ts": "2026-11-25T00:20:00Z",
        "line": f"MRB {REPO}#9842",
        "url": f"https://github.com/{REPO}/pull/9842",
        "title": "tip MRB",
        "state": "open",
    }


def _holds_has(home: Path, nick: str, *, now: float) -> bool:
    holds = gitclaim._load_seat_holds_unlocked(home, now)
    key = gitclaim._seat_key(nick)
    return isinstance(holds.get(key), dict)


def _hold_id(home: Path, nick: str, *, now: float) -> str:
    holds = gitclaim._load_seat_holds_unlocked(home, now)
    key = gitclaim._seat_key(nick)
    h = holds.get(key)
    if not isinstance(h, dict):
        return ""
    return str(h.get("id") or "")


def test_fr9855_idle_report_merged_hold_cleared_within_offer_timeout(home: Path):
    """Idle digest + MERGED busy hold inside offer timeout => sweep clears hold."""
    now = datetime.now(timezone.utc).timestamp()
    merged = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9789",
        "seq": 1,
        "ts": "2026-11-24T20:00:00Z",
        "line": f"MRB {REPO}#9789",
        "url": f"https://github.com/{REPO}/pull/9789",
        "title": "already merged",
        "state": "merged",
        "merged": True,
        "result": "MERGED",
        "offered_to": ME,
        "offered_ts": _ts(30),
    }
    _queue(home, unaccepted=[merged, _tip_mrb()])
    assert gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9789", "offered_ts": _ts(30)},
        via="offer",
    )
    # Do not call seat_open_job first (it may side-effect); assert hold file.
    assert _holds_has(home, ME, now=now)

    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle={ME},
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    actions = report.get("actions") or {}
    assert int(actions.get("sticky_holds") or 0) >= 1, actions
    assert int(actions.get("released") or 0) >= 1, actions
    why = gitclaim.seat_open_job(home, ME, now)
    assert "9789" not in why
    assert not str(_hold_id(home, ME, now=now)).endswith("9789")


def test_fr9855_idle_empty_working_on_clears_open_merged_pin(home: Path):
    """Report lastSeen idle AND working_on empty + MERGED pin => clear in one tick."""
    now = datetime.now(timezone.utc).timestamp()
    merged = {
        "repo": REPO,
        "task": "FIX",
        "id": "#9787",
        "seq": 1,
        "line": f"FIX {REPO}#9787",
        "url": f"https://github.com/{REPO}/pull/9787",
        "title": "merged fix ghost",
        "state": "closed",
        "merged": True,
        "result": "MERGED",
        "offered_to": ME,
        "offered_ts": _ts(45),
    }
    _queue(home, unaccepted=[merged])
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "FIX", "id": "#9787", "offered_ts": _ts(45)},
        via="offer",
    )
    assert gitclaim.worker_working_on(home, ME) == ""
    assert gitclaim.worker_list_state(home, ME) == "idle"
    assert _holds_has(home, ME, now=now)

    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle={ME},
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    assert int((report.get("actions") or {}).get("sticky_holds") or 0) >= 1
    assert gitclaim.seat_open_job(home, ME, now) == ""
    q = gitclaim.load_queue(home)
    for row in q.get("unaccepted") or []:
        if str(row.get("id") or "").endswith("9787"):
            assert not str(row.get("offered_to") or "").strip()


def test_fr9855_assign_tip_mrb_after_one_sweep_tick(home: Path):
    """Idle report + merged busy hold => assign tip MRB succeeds after one sweep."""
    now = datetime.now(timezone.utc).timestamp()
    merged = {
        "repo": REPO,
        "task": "FIX",
        "id": "#9788",
        "seq": 1,
        "line": f"FIX {REPO}#9788",
        "url": f"https://github.com/{REPO}/pull/9788",
        "title": "merged fix",
        "state": "closed",
        "merged": True,
        "result": "MERGED",
        "offered_to": ME,
        "offered_ts": _ts(40),
    }
    tip = _tip_mrb()
    _queue(home, unaccepted=[merged, tip])
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "FIX", "id": "#9788", "offered_ts": _ts(40)},
        via="offer",
    )
    assert _holds_has(home, ME, now=now)

    # Sole live/idle seat so idle-offer push does not steal the tip for OTHER.
    sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle={ME},
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    why = gitclaim.seat_open_job(home, ME, now)
    # Sweep may have already idle-offered the tip to ME; that is success too.
    if why == "":
        st, job = gitclaim.offer_focus_top(home, ME, SHOP, now=now)
        assert st == "ok"
        assert job is not None
        assert str(job.get("task")).upper() == "MRB"
        assert str(job.get("id") or "").endswith("9842")
    else:
        assert "9788" not in why
        assert "9842" in why or why.startswith(("offered ", "held "))
        q = gitclaim.load_queue(home)
        tip_row = next(
            (
                r
                for r in (q.get("unaccepted") or [])
                if str(r.get("id") or "").endswith("9842")
            ),
            None,
        )
        assert tip_row is not None
        assert str(tip_row.get("offered_to") or "") == ME


def test_fr9855_keeps_fresh_open_offer_pin(home: Path):
    """Fresh open offer with live pin must stay inside timeout (not ghost)."""
    now = datetime.now(timezone.utc).timestamp()
    open_mrb = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9001",
        "seq": 1,
        "line": f"MRB {REPO}#9001",
        "url": f"https://github.com/{REPO}/pull/9001",
        "title": "fresh open",
        "state": "open",
        "offered_to": ME,
        "offered_ts": _ts(20),
    }
    _queue(home, unaccepted=[open_mrb])
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9001", "offered_ts": _ts(20)},
        via="offer",
    )
    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle=set(),  # avoid idle-offer re-stamp noise; pin still live
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    why = gitclaim.seat_open_job(home, ME, now)
    assert why.startswith(("offered ", "held ")), why
    assert int((report.get("actions") or {}).get("sticky_holds") or 0) == 0


def test_fr9855_done_job_hold_with_idle_empty_clears(home: Path):
    """DONE[] finished job + idle empty working_on => clear ghost hold in sweep."""
    now = datetime.now(timezone.utc).timestamp()
    # Keep a twin unaccepted open row so FR #4415 does not void the hold on read;
    # mark it MERGED/CLOSED via done[] + result on a matching hold id.
    twin = {
        "repo": REPO,
        "task": "MRB",
        "id": "#9789",
        "seq": 1,
        "line": f"MRB {REPO}#9789",
        "url": f"https://github.com/{REPO}/pull/9789",
        "title": "done twin still queued",
        "state": "open",
        "offered_to": ME,
        "offered_ts": _ts(35),
    }
    _queue(
        home,
        unaccepted=[twin, _tip_mrb()],
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9789",
                "result": "MERGED",
                "merged": True,
                "nick": OTHER,
                "line": f"MRB {REPO}#9789",
            }
        ],
    )
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9789", "offered_ts": _ts(35)},
        via="offer",
    )
    assert _holds_has(home, ME, now=now)
    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle={ME},
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    assert int((report.get("actions") or {}).get("sticky_holds") or 0) >= 1
    assert not gitclaim.seat_open_job(home, ME, now).startswith("held ")
    assert "9789" not in gitclaim.seat_open_job(home, ME, now)
