# -*- coding: utf-8 -*-
"""FR #9783: stuck-sweep releases stale sticky via=offer holds (not released=0)."""
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
ME = "flamingo-17068"
SHOP = "#flamingo"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen", "walrus"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-11-24T18:08:00Z"},
        {
            "nick": "flamingo-99999",
            "state": "idle",
            "work": "",
            "updated": "2026-11-24T18:08:00Z",
        },
    ]
    bobreport.save_digest(tmp_path, digest)
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _queue(home: Path, unaccepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": unaccepted, "accepted": [], "done": [], "workers": {}},
    )


def test_fr9783_stuck_sweep_releases_stale_via_offer_hold(home: Path):
    """Pin already gone; via=offer hold past offer timeout → sweep released>=1."""
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9731",
                "seq": 1,
                "ts": "2026-11-24T17:50:00Z",
                "line": f"MRB {REPO}#9731",
                "url": f"https://github.com/{REPO}/pull/9731",
                "title": "MRB 9731",
                "state": "open",
            }
        ],
    )
    assert gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9731", "offered_ts": _ts(120)},
        via="offer",
    )
    assert gitclaim.seat_open_job(home, ME, now).startswith("held MRB")

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
    assert int(actions.get("released") or 0) >= 1, actions
    assert int(actions.get("sticky_holds") or 0) >= 1, actions
    why = gitclaim.seat_open_job(home, ME, now)
    # Must not stay busy (held …). A fresh idle-offer push may stamp offered_to.
    assert not why.startswith("held "), why


def test_fr9783_fail_when_released_zero_while_sticky_holds_remain(home: Path):
    """Fail-when: released=0 must not leave stale via=offer holds on idle nicks."""
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9717",
                "seq": 1,
                "ts": "2026-11-24T17:50:00Z",
                "line": f"MRB {REPO}#9717",
                "url": f"https://github.com/{REPO}/pull/9717",
                "title": "MRB 9717",
                "state": "open",
            }
        ],
    )
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9717", "offered_ts": _ts(180)},
        via="offer",
    )
    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME},
        idle={ME},
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    why = gitclaim.seat_open_job(home, ME, now)
    released = int((report.get("actions") or {}).get("released") or 0)
    assert not (released == 0 and why.startswith("held ")), (released, why)


def test_fr9783_keeps_fresh_via_offer_and_ack_missing(home: Path):
    """Within offer timeout and ack-missing holds stay (FR #3192 / #4115)."""
    now = datetime.now(timezone.utc).timestamp()
    other = "flamingo-99999"
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9001",
                "seq": 1,
                "ts": "2026-11-24T18:00:00Z",
                "line": f"MRB {REPO}#9001",
                "url": f"https://github.com/{REPO}/pull/9001",
                "title": "MRB 9001",
                "state": "open",
                "offered_to": ME,
                "offered_ts": _ts(30),
            }
        ],
    )
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9001", "offered_ts": _ts(30)},
        via="offer",
    )
    gitclaim.note_seat_hold(
        home,
        other,
        {"repo": REPO, "task": "FR", "id": "#9002", "offered_ts": _ts(600)},
        via="ack-missing",
    )
    before = gitclaim.seat_open_job(home, ME, now)
    report = sjs.run_stuck_sweep(
        home,
        now=now,
        live={ME, other},
        idle=set(),  # avoid idle-offer re-stamp noise
        act=True,
        open_items=[],
        fuel_ok=True,
    )
    assert before.startswith(("offered ", "held "))
    assert gitclaim.seat_open_job(home, ME, now).startswith(("offered ", "held "))
    assert gitclaim.seat_open_job(home, other, now).startswith("held ")
    # Fresh offer must not inflate sticky_holds for this class alone.
    assert int((report.get("actions") or {}).get("sticky_holds") or 0) == 0
