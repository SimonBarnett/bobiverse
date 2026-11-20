"""FR #7912: a holder's own repeated !bored releases the job."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"
ME = "flamingo-19496"
OTHER = "flamingo-11072"
SHOP = "#flamingo"


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_HOLDER_BORED_N", raising=False)
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": ME, "state": "doing", "work": "bobiverse MRB #7890", "updated": _ts(0)},
        {"nick": OTHER, "state": "idle", "work": "", "updated": _ts(0)},
    ]
    bobreport.save_digest(tmp_path, digest)
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _row(task: str, num: int) -> dict:
    return {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-11-16T10:00:00Z",
        "line": f"{task} {REPO}#{num}",
        "url": f"https://github.com/{REPO}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }


def _queue(home: Path, unaccepted: list, accepted: list | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": unaccepted, "accepted": accepted or [], "done": [], "workers": {}},
    )


def _accepted(num: int, nick: str = ME) -> dict:
    row = _row("MRB", num)
    row["nick"] = nick
    row["accepted_ts"] = _ts(30)
    return row


def test_two_bored_from_holder_releases_and_next_offer_is_not_nak(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    reports = []
    monkeypatch.setattr(
        gitclaim,
        "_report_holder_bored",
        lambda nick, job: reports.append((nick, job)),
    )
    _queue(home, [_row("FR", 8000)], [_accepted(7890)])
    now = time.time()
    assert gitclaim.bored_gate(home, ME, SHOP, now, session_started=0.0) == "busy"
    assert gitclaim.release_holder_on_bored(home, ME, now) == ""
    assert gitclaim.seat_open_job(home, ME, now).startswith("accepted MRB")
    released = gitclaim.release_holder_on_bored(home, ME, now + 1)
    assert released.startswith("accepted MRB")
    assert "7890" in released
    assert gitclaim.seat_open_job(home, ME, now + 1) == ""
    assert gitclaim.bored_gate(home, ME, SHOP, now + 2, session_started=0.0) == "ok"
    status, job = gitclaim.offer_focus_top(home, ME, SHOP, now=now + 2)
    assert status == "ok" and job is not None
    assert job["id"] == "#8000"
    doc = gitclaim._load_queue_unlocked(home)
    back = [r for r in doc["unaccepted"] if str(r.get("id")) == "#7890"]
    assert len(back) == 1
    # FR #8375 / #8397: holder_bored is infra-soft. Releasing the row must not
    # burn giveup_count or stamp needs_human. Seat exclusion and cooldown stay.
    assert int(back[0].get("giveup_count") or 0) == 0
    assert not back[0].get("needs_human")
    assert "flamingo-19496" in str(back[0].get("giveup_seats") or "")
    assert back[0].get("cooldown_until")
    assert reports and reports[0][0] == ME
    assert "7890" in reports[0][1]


def test_other_seat_bored_does_not_release_holder(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "_report_holder_bored", lambda nick, job: None)
    _queue(home, [_row("FR", 8000)], [_accepted(7890, ME)])
    now = time.time()
    assert gitclaim.release_holder_on_bored(home, OTHER, now) == ""
    assert gitclaim.release_holder_on_bored(home, OTHER, now + 1) == ""
    assert gitclaim.seat_open_job(home, ME, now).startswith("accepted MRB")
    doc = gitclaim._load_queue_unlocked(home)
    assert any(str(r.get("id")) == "#7890" for r in doc["accepted"])


def test_ack_or_progress_resets_the_streak(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "_report_holder_bored", lambda nick, job: None)
    _queue(home, [_row("FR", 8000)], [_accepted(7890)])
    now = time.time()
    assert gitclaim.release_holder_on_bored(home, ME, now) == ""
    gitclaim.reset_holder_bored(home, ME)
    assert gitclaim.release_holder_on_bored(home, ME, now + 1) == ""
    assert gitclaim.seat_open_job(home, ME, now).startswith("accepted MRB")
    assert gitclaim.release_holder_on_bored(home, ME, now + 2).startswith("accepted MRB")
