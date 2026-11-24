# -*- coding: utf-8 -*-
"""FR #9771: sticky via=offer seat-hold must clear on !bored / !cleargiveup (regression after #9633)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
ME = "redqueen-11500"
SHOP = "#redqueen"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo", "walrus"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-11-24T18:06:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _queue(home: Path, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": unaccepted, "accepted": accepted or [], "done": [], "workers": {}},
    )


def test_fr9771_bored_clears_stale_via_offer_hold_without_pin(home: Path):
    """Pin already gone; via=offer hold still paints held → !bored must free the seat."""
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
                # no offered_to — pin already purged
            }
        ],
    )
    ok = gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9717", "offered_ts": _ts(120)},
        via="offer",
    )
    assert ok is True
    why = gitclaim.seat_open_job(home, ME, now)
    assert why.startswith("held MRB"), why
    cleared = gitclaim.release_sticky_offer_on_bored(home, ME, now)
    assert cleared
    assert "9717" in cleared
    assert gitclaim.seat_open_job(home, ME, now) == ""
    assert gitclaim.bored_gate(home, ME, SHOP, now) == "ok"


def test_fr9771_cleargiveup_clears_seat_hold(home: Path):
    """!cleargiveup must drop matching seat-holds (ledger=0 alone left busy held)."""
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9717",
                "seq": 1,
                "line": f"MRB {REPO}#9717",
                "url": f"https://github.com/{REPO}/pull/9717",
                "giveup_seats": [ME],
                "giveup_count": 1,
            }
        ],
    )
    assert gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9717", "offered_ts": _ts(30)},
        via="offer",
    )
    assert gitclaim.seat_open_job(home, ME, now).startswith("held MRB")
    out = gitclaim.clear_giveup_job(home, REPO, "#9717", seat=ME)
    assert out.get("ok") is True
    assert gitclaim.seat_open_job(home, ME, now) == ""


def test_fr9771_ack_missing_hold_stays_on_bored(home: Path):
    """FR #4115 ack-missing must remain busy (do not regress #9633/#9709 gate)."""
    now = datetime.now(timezone.utc).timestamp()
    _queue(home, [])
    assert gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "FR", "id": "#4115", "offered_ts": _ts(120)},
        via="ack-missing",
    )
    assert gitclaim.release_sticky_offer_on_bored(home, ME, now) == ""
    assert gitclaim.seat_open_job(home, ME, now).startswith("held FR")
    assert gitclaim.bored_gate(home, ME, SHOP, now) == "busy"


def test_fr9771_fresh_via_offer_hold_stays_busy(home: Path):
    """Within offer timeout, via=offer hold stays (FR #8738 / #3192)."""
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9731",
                "seq": 1,
                "line": f"MRB {REPO}#9731",
                "url": f"https://github.com/{REPO}/pull/9731",
                "offered_to": ME,
                "offered_ts": _ts(30),
                "offered_via": "offer",
            }
        ],
    )
    assert gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#9731", "offered_ts": _ts(30)},
        via="offer",
    )
    assert gitclaim.release_sticky_offer_on_bored(home, ME, now) == ""
    assert gitclaim.bored_gate(home, ME, SHOP, now) == "busy"
