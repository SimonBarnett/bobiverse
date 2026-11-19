"""FR #8344: a seat that holds the row is not an all-gave-up stall."""
from __future__ import annotations

import gitclaim
import shop_listen
import stall_detectors as sd


def test_holder_is_not_counted_as_gave_up():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8343",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/8343",
        "nick": "flamingo-16976",
        "giveup_seats": "flamingo-10852,flamingo-16976",
    }
    snap = {
        "live": {"flamingo-10852", "flamingo-16976"},
        "accepted": [row],
        "unaccepted": [],
    }
    assert sd.detect_all_gave_up(snap) == []


def test_all_gave_up_still_fires_when_nobody_holds_the_row():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8343",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/8343",
        "giveup_seats": "flamingo-10852,flamingo-16976",
    }
    snap = {
        "live": {"flamingo-10852", "flamingo-16976"},
        "unaccepted": [row],
    }
    found = sd.detect_all_gave_up(snap)
    assert len(found) == 1
    assert found[0]["id"] == "all-gave-up"


def test_ack_drops_stale_giveup_seat(tmp_path):
    row = {
        "v": 1,
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8343",
        "title": "lesson",
        "line": "x",
        "ts": "t",
        "seq": 1,
        "giveup_seats": "flamingo-10852,flamingo-16976",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    status, job = shop_listen.accept_job_by_ref(
        tmp_path,
        nick="flamingo-16976",
        channel="#flamingo",
        repo="SimonBarnett/bobiverse",
        task="MRB",
        ident="#8343",
    )
    assert status == "ok"
    seats = str(job.get("giveup_seats") or "")
    assert "flamingo-16976" not in seats.lower()
    assert "flamingo-10852" in seats.lower()
