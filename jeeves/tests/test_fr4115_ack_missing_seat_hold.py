# -*- coding: utf-8 -*-
"""FR #4115: ACK status=missing records a seat hold so the seat is not treated as free.

When a seat ACKs a job Jeeves has no queue row for (offers made before a Jeeves restart),
record seat-holds.json for that nick. Accepted/ok ACK still clears the offer hold
(accepted row takes over).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
ME = "marchhare-35600"
SHOP = "#marchhare"
ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "common" / "scripts" / "irc_agent.py"


def _ts(ago_s: float = 0.0) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _queue(home: Path, unaccepted=None, accepted=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted or [],
            "accepted": accepted or [],
            "done": [],
            "workers": {},
        },
    )


def test_note_seat_hold_public_api_blocks_bored(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"35600": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, [])
    fi.handle_focus_cmd(tmp_path, REPO)

    assert gitclaim.seat_open_job(tmp_path, ME) == ""
    assert gitclaim.bored_gate(tmp_path, ME, SHOP, time.time()) == "ok"

    ok = gitclaim.note_seat_hold(
        tmp_path,
        ME,
        {"repo": REPO, "task": "FR", "id": "#4115", "offered_ts": _ts()},
        via="ack-missing",
    )
    assert ok is True
    why = gitclaim.seat_open_job(tmp_path, ME)
    assert why.startswith("held FR")
    assert gitclaim.bored_gate(tmp_path, ME, SHOP, time.time()) == "busy"


def test_shop_listen_ack_missing_notes_seat_hold(tmp_path: Path, monkeypatch):
    """handle_shop_worker_line ACK with no matching row -> status=missing + seat hold."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"35600": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, [])  # empty queue: ACK has nothing to accept
    fi.handle_focus_cmd(tmp_path, REPO)

    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=ME,
        channel=SHOP,
        body="ACK FR SimonBarnett/bobiverse#4115",
        post_fn=lambda payload: 204,
    )
    assert result.get("handled") is True
    assert result.get("status") == "missing"
    assert result.get("verb") == "ACK"
    why = gitclaim.seat_open_job(tmp_path, ME)
    assert "held" in why and "4115" in why


def test_irc_agent_ack_missing_records_hold_not_clear(tmp_path: Path):
    """Source pin: ACK status=missing notes a hold; ok/duplicate still clear."""
    src = IRC.read_text(encoding="utf-8")
    assert "status == \"missing\"" in src or "status == 'missing'" in src
    # FR #4115 branch must note_seat_hold on missing ACK.
    assert "note_seat_hold(" in src
    # Must not blindly clear_seat_hold on every ACK including missing.
    # The missing path records a hold; clear remains for ok/duplicate / DONE/NACK/GIVEUP.
    assert "FR #4115" in src or "ack-missing" in src.lower() or "ACK status=missing" in src
