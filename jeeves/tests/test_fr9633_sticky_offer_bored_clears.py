# -*- coding: utf-8 -*-
"""FR #9633: !bored while only sticky-offered must clear the pin (not NAK busy forever)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
ME = "redqueen-10704"
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
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-11-24T13:53:00Z"},
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


def test_fr9633_bored_gate_ok_after_sticky_offer_release(home: Path):
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9625",
                "seq": 1,
                "ts": "2026-11-24T13:50:00Z",
                "line": f"MRB {REPO}#9625",
                "url": f"https://github.com/{REPO}/pull/9625",
                "title": "MRB 9625",
                "state": "open",
                "offered_to": ME,
                "offered_ts": _ts(30),
                "offered_via": "offer",
            }
        ],
    )
    # Pre-clear: sticky offer is visible as open/pending work
    open_before = gitclaim.seat_open_job(home, ME, now)
    assert open_before and "9625" in open_before
    assert gitclaim.seat_pending_offer(home, ME, now) is not None
    cleared = gitclaim.release_sticky_offer_on_bored(home, ME, now)
    assert cleared
    assert "9625" in cleared
    doc = gitclaim.load_queue(home)
    assert not any(
        str(r.get("offered_to") or "").strip()
        for r in (doc.get("unaccepted") or [])
        if isinstance(r, dict)
    )
    # bored_gate clears sticky offers (FR #9633) then returns ok
    assert gitclaim.bored_gate(home, ME, SHOP, now) == "ok"


def test_fr9633_does_not_clear_accepted_row(home: Path):
    now = datetime.now(timezone.utc).timestamp()
    _queue(
        home,
        [],
        accepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#9625",
                "nick": ME,
                "accepted_by": ME,
                "accepted_ts": _ts(10),
                "line": f"MRB {REPO}#9625",
                "url": f"https://github.com/{REPO}/pull/9625",
            }
        ],
    )
    assert gitclaim.release_sticky_offer_on_bored(home, ME, now) == ""
    assert gitclaim.bored_gate(home, ME, SHOP, now) == "busy"
