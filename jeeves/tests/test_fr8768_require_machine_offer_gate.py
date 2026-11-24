"""FR #8768: chair must not offer require_machine=walrus FRs into #marchhare.

Honor-path GIVEUP on the wrong shop stays (FR #1688 / #8653); offer_focus_top
must not stamp offered_to for a mismatched seat. A GIVEUP reason of
require_machine=<mid> must stamp that pin on the row so the next !bored skips
wrong shops.
"""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-11-21T12:00:00Z",
            }
            for pid in workers
        ]
    bobreport.save_digest(home, doc)


def test_fr8768_seat_matches_uses_nick_fallback_without_digest_roster(monkeypatch):
    """Cold digest must still parse <machine>-<pid> for the require_machine gate."""
    monkeypatch.setattr(bobreport, "seat_machine_ids", lambda: ())
    assert gitclaim.seat_matches_require_machine("walrus-4", "walrus") is True
    assert gitclaim.seat_matches_require_machine("marchhare-12400", "walrus") is False
    assert gitclaim.seat_matches_require_machine("marchhare-12400", "ionos") is False
    assert gitclaim.row_blocked_for_machine(
        {
            "require_machine": "walrus",
            "repo": "other/x",
            "id": "1",
            "title": "t",
            "body": "",
        },
        "marchhare-12400",
    )


def test_fr8768_offer_focus_skips_walrus_pin_for_marchhare(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"walrus": [9], "marchhare": [12400], "ionos": [1]})
    body = (
        "Fix the chair offer gate.\n\n"
        "Acceptance: Sync/compose on walrus.\n"
        "require_machine: walrus\n"
    )
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8768",
        "seq": 1,
        "ts": "t",
        "line": "chair offer gate",
        "title": "chair: do not offer require_machine=walrus FRs into #marchhare shop",
        "body": gitclaim._body_for_queue(body),
        # FR #9637: body pin alone no longer stamps; needs-walrus label does.
        "labels": ["feature-request", "needs-walrus"],
        "state": "open",
    }
    assert gitclaim.row_require_machine(row) == "walrus"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    fi.handle_focus_cmd(home, "hi bobiverse")

    status, job = gitclaim.offer_focus_top(home, "marchhare-12400", "#marchhare")
    assert status == "empty"
    assert job is None

    status2, job2 = gitclaim.offer_focus_top(home, "walrus-9", "#walrus")
    assert status2 == "ok"
    assert job2 is not None
    assert str(job2.get("id") or "") in ("#8768", "8768")
    assert str(job2.get("offered_to") or "").lower().startswith("walrus-")


def test_fr8768_parse_and_stamp_require_machine_giveup_reason(monkeypatch):
    monkeypatch.setattr(bobreport, "seat_machine_ids", lambda: ("walrus", "marchhare"))
    assert gitclaim.parse_require_machine_giveup_reason("require_machine=walrus") == "walrus"
    assert (
        gitclaim.parse_require_machine_giveup_reason(
            "wrong shop; require_machine=walrus (honor pin)"
        )
        == "walrus"
    )
    assert gitclaim.parse_require_machine_giveup_reason("out of fuel") == ""
    row: dict = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "8738",
        "title": "x",
        "body": "no pin here yet",
        "labels": [],
    }
    gitclaim.apply_require_machine_giveup_stamp(row, "require_machine=walrus")
    assert row.get("require_machine") == "walrus"
    assert row.get("require_machine_operator") is True
    assert gitclaim.row_blocked_for_machine(row, "marchhare-1")
    assert not gitclaim.row_blocked_for_machine(row, "walrus-1")
