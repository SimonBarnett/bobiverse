# -*- coding: utf-8 -*-
"""FR #7837: pause offers while a fresh digest pool is 0% until reset."""
from __future__ import annotations

import json

import bobreport
import gitclaim
import registered_machines
import shop_listen

RESET = "2026-11-22T19:28:00Z"
NOW = 1_763_300_000.0
NICK = "flamingo-19156"
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _digest(home, pool: dict, *, kind: str = "grok") -> None:
    doc = {
        "v": 1,
        "machines": {
            "flamingo": {
                "id": "flamingo",
                "xai_weekly": pool,
                "workers": {
                    "19156": {
                        "pid": "19156",
                        "nick": NICK,
                        "kind": kind,
                        "state": "running",
                    }
                },
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home, *, accepted=False) -> None:
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#7800",
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/7800",
    }
    if accepted:
        row["nick"] = NICK
    bucket = "accepted" if accepted else "unaccepted"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [] if accepted else [row], "accepted": [row] if accepted else [], "done": []},
    )


def _zero_pool(**extra):
    pool = {
        "remaining_pct": 0,
        "fresh": True,
        "fetched_at": "2026-11-16T00:00:00Z",
        "period_end": RESET,
    }
    pool.update(extra)
    return pool


def test_fr7837_fresh_zero_pauses_and_blocks_offer(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, _zero_pool())
    _queue(home)
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == "pool-0-until-reset"
    loaded = bobreport.load_digest(home)
    worker = loaded["machines"]["flamingo"]["workers"]["19156"]
    assert worker["fuel_paused_until"] == RESET
    assert worker["fuel_pause_reason"] == "pool-0-until-reset"
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "empty" and job is None
    queued = json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))
    assert queued["unaccepted"][0]["id"] == "#7800"
    assert not queued["unaccepted"][0].get("offered_to")


def test_fr7837_pause_clears_after_reset_or_fresh_percent(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, _zero_pool())
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == "pool-0-until-reset"
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW + 40_000_000) == ""
    loaded = bobreport.load_digest(home)
    assert "fuel_paused_until" not in loaded["machines"]["flamingo"]["workers"]["19156"]
    _digest(home, _zero_pool(remaining_pct=12))
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == ""


def test_fr7837_stale_zero_does_not_pause(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, _zero_pool(fresh=False))
    _queue(home)
    assert gitclaim.seat_fuel_pause_reason(home, NICK, NOW) == ""
    status, job = gitclaim.offer_focus_top(home, NICK, "#flamingo", now=NOW)
    assert status == "ok" and job and job["id"] == "#7800"


def test_fr7837_exhausted_giveup_does_not_count(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _digest(home, _zero_pool())
    _queue(home, accepted=True)
    status, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#7800",
        now=NOW,
        reason="no-terminal-reply",
    )
    assert status == "ok"
    assert job.get("giveup_count") in (None, 0)
    assert not job.get("needs_human")
    assert not job.get("cooldown_until")
    assert not job.get("giveup_seats")
