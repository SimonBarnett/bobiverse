# -*- coding: utf-8 -*-
"""FR #9406 / #9402: hold-gated FR sticky offered_to must not busy a seat."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines

NICK = "flamingo-4120"
OTHER = "redqueen-6400"


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-23T17:50:00Z"},
    ]
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": OTHER, "state": "idle", "work": "", "updated": "2026-11-23T17:50:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _held_offered_row(**extra) -> dict:
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9376",
        "title": "After Depends-on: rebuild jeeves on walrus",
        "labels": ["feature-request", "hold", "via-intake"],
        "body": "Ops install NOT done.\nDepends-on: #155\n## GateIssues\n",
        "line": "FR SimonBarnett/bobiverse#9376",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9376",
        "offered_to": NICK,
        "offered_ts": "2026-11-23T17:50:00Z",
        "offered_channel": "#flamingo",
        "seq": 1,
    }
    row.update(extra)
    return row


def test_fr9406_clear_held_fr_sticky_offers_drops_row():
    doc = {"unaccepted": [_held_offered_row()], "accepted": [], "done": []}
    dropped = gitclaim.clear_held_fr_sticky_offers(doc)
    assert dropped
    assert doc["unaccepted"] == []


def test_fr9406_seat_not_busy_and_queue_purged(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_held_offered_row()],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    assert gitclaim.seat_open_job(home, NICK, now=1_700_000_000.0) == ""
    q = gitclaim.load_queue(home)
    assert not any(str(r.get("id") or "").endswith("9376") for r in q.get("unaccepted") or [])


def test_fr9406_offer_focus_top_purges_held_sticky(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _held_offered_row(),
                {
                    "repo": "SimonBarnett/skills-visionary",
                    "task": "MRB",
                    "id": "#208",
                    "title": "VIS-G1",
                    "url": "https://github.com/SimonBarnett/skills-visionary/pull/208",
                    "line": "MRB",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {OTHER: {"last_seen": 9e12}, NICK: {"last_seen": 9e12}},
        },
    )
    st, job = gitclaim.offer_focus_top(home, OTHER, "#redqueen", now=1_700_000_000.0)
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "MRB"
    q = gitclaim.load_queue(home)
    assert not any(str(r.get("id") or "").endswith("9376") for r in q.get("unaccepted") or [])


def test_fr9406_non_hold_offer_still_busy(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = _held_offered_row(labels=["feature-request"])
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    open_job = gitclaim.seat_open_job(home, NICK, now=1_700_000_000.0)
    assert "offered" in open_job and "9376" in open_job


def test_fr9406_digest_hold_keeps_row_clears_offer():
    doc = {
        "unaccepted": [
            _held_offered_row(
                labels=["fr-digest", "hold"],
                body="Kind: fr-digest\n",
            )
        ],
        "accepted": [],
        "done": [],
    }
    dropped = gitclaim.clear_held_fr_sticky_offers(doc)
    assert dropped
    assert len(doc["unaccepted"]) == 1
    assert not doc["unaccepted"][0].get("offered_to")
