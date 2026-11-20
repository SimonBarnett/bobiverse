"""FR #8428: an offer-timeout is re-offered to a different live idle seat."""

from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines as rm
import stuck_job_sweep as sweep


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#flamingo", "#redqueen"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row():
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "FIX",
        "id": "#8385",
        "seq": 1,
        "ts": "2026-11-20T10:00:00Z",
        "line": "x",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/8385",
        "giveup_count": 0,
    }


def test_fr8428_timeout_marks_seat_for_a_different_push(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = _row()
    gitclaim.note_unanswered_offer(row, "flamingo-22532", time.time())
    assert row["offer_unanswered"]["flamingo-22532"] == 1
    assert row["offer_last_timeout_seat"] == "flamingo-22532"
    assert "flamingo-22532" not in (row.get("offer_refused_by") or [])
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    doc = bobreport.load_digest(home)
    for mid, nick in (("flamingo", "flamingo-22532"), ("redqueen", "redqueen-9")):
        ent = doc["machines"].setdefault(mid, bobreport._empty_machine(mid))
        ent["online"] = True
        ent["worker_list"] = [{"nick": nick, "state": "idle", "work": ""}]
    bobreport.save_digest(home, doc)
    now = time.time()
    gitclaim.note_idle_after_empty(home, "flamingo-22532", "#flamingo", now=now)
    gitclaim.note_idle_after_empty(home, "redqueen-9", "#redqueen", now=now)
    said = []
    sent = gitclaim.offer_to_idle_seats(home, say=lambda ch, text: said.append((ch, text)) or True, now=now + 5)
    assert sent == 1
    assert said[0][0] == "#redqueen"
    held = gitclaim.load_unaccepted(home)[0]
    assert held["offered_to"] == "redqueen-9"
    assert "offer_last_timeout_seat" not in held


def test_fr8428_starved_flags_other_machine_idle():
    row = _row()
    row["offer_last_timeout_seat"] = "flamingo-22532"
    classified = sweep.classify_queue_row(
        row,
        bucket="unaccepted",
        now=time.time(),
        live={"flamingo-22532", "redqueen-9"},
        idle={"redqueen-9"},
        home=None,
        ledger={},
    )
    assert classified["stuck_reason"] == "unaccepted_starved"
    assert classified.get("other_machine_idle") is True
    alert = sweep.other_machine_idle_alert([classified])
    assert alert.startswith("other_machine_idle=1")
    assert "SimonBarnett/bobiverse#8385" in alert
    assert sweep.other_machine_idle_alert(
        [{"stuck": True, "stuck_reason": "unaccepted_starved"}]
    ) == ""
