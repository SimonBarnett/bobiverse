# -*- coding: utf-8 -*-
"""FR #8592: skip new opencode offers when opencode-go week window is limited."""
from __future__ import annotations

import json

import bobreport
import gitclaim
import registered_machines

NOW = 1_763_830_000.0
RESET = "2026-11-23T00:00:00Z"
NICK = "flamingo-16764"
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _digest(home, *, week_limited: bool, kind: str = "opencode", start_model: str = "opencode-go/deepseek-v4-pro"):
    week = {
        "status": "exhausted" if week_limited else "known",
        "used_pct": 100 if week_limited else 40,
        "remaining_pct": 0 if week_limited else 60,
        "limited": week_limited,
        "resets_at": RESET,
        "fetched_at": "2026-11-20T23:05:27Z",
    }
    rolling = {
        "status": "known",
        "used_pct": 33,
        "remaining_pct": 67,
        "limited": False,
        "fetched_at": "2026-11-20T23:05:27Z",
    }
    # Machine go pool still shows rolling remaining so old pause path alone would not fire.
    machine_pool = {
        "remaining_pct": 67,
        "fresh": True,
        "fetched_at": "2026-11-20T23:05:27Z",
        "period_end": RESET,
        "windows": {"rolling": rolling, "week": week},
    }
    doc = {
        "v": 1,
        "fleet_pools": {
            "opencode-go": {
                "remaining": 67,
                "windows": {"rolling": rolling, "week": week},
                "fetched_at": "2026-11-20T23:05:27Z",
            }
        },
        "opencode": {"windows": {"rolling": rolling, "week": week}},
        "machines": {
            "flamingo": {
                "id": "flamingo",
                "opencode": machine_pool,
                "workers": {
                    "16764": {
                        "pid": "16764",
                        "nick": NICK,
                        "kind": kind,
                        "state": "idle",
                        "start_model": start_model,
                        "model": start_model,
                    }
                },
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home) -> None:
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8592",
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/8592",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )


def test_week_limited_blocks_opencode_go_offer(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, week_limited=True)
    _queue(home)
    reason = gitclaim.seat_fuel_pause_reason(home, NICK, NOW)
    assert reason == "opencode-week-limited"
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "empty" and job is None
    queued = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    assert queued["unaccepted"][0]["id"] == "#8592"
    assert not queued["unaccepted"][0].get("offered_to")


def test_week_not_limited_still_offers(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, week_limited=False)
    _queue(home)
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == ""
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "ok" and job and job["id"] == "#8592"


def test_week_limited_does_not_pause_grok_seat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, week_limited=True, kind="grok", start_model="grok-4")
    # grok needs xai pool or no pause
    doc = bobreport.load_digest(home)
    doc["machines"]["flamingo"]["xai_weekly"] = {
        "remaining_pct": 50,
        "fresh": True,
        "fetched_at": "2026-11-20T23:05:27Z",
        "period_end": RESET,
    }
    bobreport.save_digest(home, doc)
    _queue(home)
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == ""
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "ok" and job and job["id"] == "#8592"


def test_week_limited_free_opencode_not_gated_by_week(tmp_path, monkeypatch):
    """Free OpenCode seats use free-pool pause, not the Go week window."""
    home = _home(tmp_path, monkeypatch)
    _digest(
        home,
        week_limited=True,
        kind="opencode",
        start_model="opencode/deepseek-v4.1-flash-free",
    )
    doc = bobreport.load_digest(home)
    # free pool still has remaining so free pause does not fire
    doc["machines"]["flamingo"]["pcent"] = {"opencode-free": 80, "opencode-go": 0}
    bobreport.save_digest(home, doc)
    _queue(home)
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == ""
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "ok" and job and job["id"] == "#8592"
