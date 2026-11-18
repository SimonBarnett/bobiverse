# -*- coding: utf-8 -*-
"""FR #8154: console-closed GIVEUP re-offers promptly and prefers same machine."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT = "flamingo-37200"
FRESH_SAME = "flamingo-48824"
OTHER = "marchhare-18680"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {
        "37200": {"state": "idle", "nick": SEAT},
        "48824": {"state": "idle", "nick": FRESH_SAME},
    }
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "18680": {"state": "idle", "nick": OTHER},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_is_console_closed_reason_matches_wire():
    assert gitclaim.is_console_closed_reason("console-closed") is True
    assert gitclaim.is_console_closed_reason("CONSOLE-CLOSED") is True
    assert gitclaim.is_console_closed_reason("console-closed wip=fr-8154:abc") is True
    assert gitclaim.is_console_closed_reason("out-of-fuel") is False
    assert gitclaim.is_console_closed_reason("") is False
    assert gitclaim.console_closed_wip_ref("console-closed wip=fr-8154:abcdef012345") == (
        "fr-8154:abcdef012345"
    )


def test_console_closed_giveup_no_cooldown_stamps_require_machine(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8154",
        "nick": SEAT,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/issues/8154",
        "title": "console close",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#8154",
        now=time.time(),
        reason="console-closed wip=fr-8154:abcdef012345",
    )
    assert st == "ok" and job is not None
    assert int(job.get("giveup_count") or 0) == 0
    assert not job.get("needs_human")
    assert not str(job.get("cooldown_until") or "").strip()
    assert job.get("require_machine") == "flamingo"
    assert job.get("require_machine_operator") is True
    assert job.get("console_closed_wip") == "fr-8154:abcdef012345"
    # Exact dead nick may sit in giveup_seats; a fresh same-machine seat stays offerable.
    seats = str(job.get("giveup_seats") or "")
    assert SEAT in seats or SEAT.lower() in seats.lower()

    # Same-machine fresh seat can take it (require_machine pin).
    st2, offered = gitclaim.offer_focus_top(
        home, FRESH_SAME, "#flamingo", now=time.time() + 10
    )
    assert st2 == "ok" and offered["id"] == "#8154"

    # Other machine is gated by require_machine=flamingo.
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [dict(job)], "accepted": [], "done": []},
    )
    st3, offered3 = gitclaim.offer_focus_top(
        home, OTHER, "#marchhare", now=time.time() + 20
    )
    assert st3 != "ok" or offered3 is None or offered3.get("id") != "#8154"
