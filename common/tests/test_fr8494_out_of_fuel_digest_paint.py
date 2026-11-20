"""FR #8494: out-of-fuel hold paints digest state and skips idle_quiet_offerable."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import focus_ignore
import gitclaim
import registered_machines
import stuck_job_sweep as sweep

REPO = "SimonBarnett/bobiverse"
NICK = "flamingo-8494"
NOW = 1_900_100_000.0


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-20T15:15:10Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    focus_ignore.handle_focus_cmd(tmp_path, f"high {REPO}")
    return tmp_path


def _offerable_fr_row(*, age_s=4000):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - float(age_s)))
    return {
        "repo": REPO,
        "task": "FR",
        "id": "#8494",
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/8494",
        "ts": ts,
        "event": "issues",
        "line": "FR",
        "title": "fuel hold paint",
        "labels": ["feature-request", "via-intake"],
    }


def test_coerce_keeps_out_of_fuel_and_work():
    rows = bobreport._coerce_worker_list(
        [{"nick": NICK, "state": "out-of-fuel", "work": "out-of-fuel", "updated": "t1"}]
    )
    assert rows[0]["state"] == "out_of_fuel"
    assert rows[0]["work"] == "out-of-fuel"


def test_mark_digest_fuel_hold_advances_updated(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    assert bobreport.mark_digest_fuel_hold(home, NICK, held=True) is True
    wl = bobreport.load_digest(home)["machines"]["flamingo"]["worker_list"]
    assert wl[0]["state"] == "out_of_fuel"
    first = wl[0]["updated"]
    assert first != "2026-11-20T15:15:10Z"
    time.sleep(1.05)
    assert bobreport.mark_digest_fuel_hold(home, NICK, held=True) is True
    wl2 = bobreport.load_digest(home)["machines"]["flamingo"]["worker_list"]
    assert wl2[0]["state"] == "out_of_fuel"
    assert wl2[0]["updated"] != first
    assert bobreport.mark_digest_fuel_hold(home, NICK, held=False) is True
    wl3 = bobreport.load_digest(home)["machines"]["flamingo"]["worker_list"]
    assert wl3[0]["state"] == "idle"
    assert wl3[0]["work"] == ""


def test_note_seat_out_of_fuel_paints_and_skips_quiet_idle(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    assert gitclaim.note_seat_out_of_fuel(home, NICK) is True
    assert gitclaim.seat_is_out_of_fuel(home, NICK) is True
    assert gitclaim.worker_list_state(home, NICK) == "out_of_fuel"
    found = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored={NICK: NOW - (sweep.QUIET_IDLE_OFFERABLE_S + 30)},
        last_activity={},
        accepted=[],
        now=NOW,
    )
    assert found == []
