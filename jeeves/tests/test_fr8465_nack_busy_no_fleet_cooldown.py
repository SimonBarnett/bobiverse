"""FR #8465: NACK busy is a seat-local backoff, not a fleet cooldown."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT_A = "flamingo-14448"
SEAT_B = "redqueen-9"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid, nick in (("flamingo", SEAT_A), ("redqueen", SEAT_B)):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["online"] = True
        digest["machines"][mid]["workers"] = {"1": {"state": "idle", "nick": nick}}
        digest["machines"][mid]["worker_list"] = [{"nick": nick, "state": "idle", "work": ""}]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_nack_busy_does_not_set_fleet_cooldown(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8455",
        "nick": SEAT_A,
        "seq": 1,
        "ts": "t",
        "line": "MRB",
        "url": f"https://github.com/{REPO}/pull/8455",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": []},
    )
    now = time.time()
    st, job = shop_listen.return_job_to_unaccepted(
        home, repo=REPO, task="MRB", ident="#8455", now=now, reason="busy"
    )
    assert st == "ok" and job is not None
    assert "cooldown_until" not in job
    assert int(job.get("giveup_count") or 0) == 0
    assert not job.get("needs_human")
    assert SEAT_A not in str(job.get("giveup_seats") or "")
    assert gitclaim.row_on_cooldown(job, now + 1, "") is False
    assert gitclaim.row_on_cooldown(job, now + 1, SEAT_B) is False
    assert gitclaim.seat_on_deterministic_nack_cooldown(job, SEAT_A, now + 1) is True
    assert gitclaim.seat_on_deterministic_nack_cooldown(job, SEAT_B, now + 1) is False
    assert gitclaim.seat_on_deterministic_nack_cooldown(
        job, SEAT_A, now + gitclaim.BUSY_NACK_BACKOFF_S + 5
    ) is False

    st_b, offered = gitclaim.offer_focus_top(home, SEAT_B, "#redqueen", now=now + 2)
    assert st_b == "ok"
    assert offered["id"] == "#8455"

    # Put the row back unaccepted and confirm A is skipped while the backoff holds.
    held = gitclaim.load_unaccepted(home)[0]
    held.pop("offered_to", None)
    held.pop("offered_ts", None)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [held], "accepted": [], "done": []},
    )
    st_a, _job_a = gitclaim.offer_focus_top(home, SEAT_A, "#flamingo", now=now + 2)
    assert st_a != "ok"
