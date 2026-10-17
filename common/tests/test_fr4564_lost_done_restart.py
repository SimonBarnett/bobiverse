"""FR #4564: LOST_DONE_RESTART must not re-offer a finished job to the same seat."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _accepted_mrb(nick: str) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "repo": "SimonBarnett/a-search",
        "task": "MRB",
        "id": "#3614",
        "seq": 1,
        "url": "https://github.com/SimonBarnett/a-search/pull/3614",
        "nick": nick,
        "accepted_by": nick,
        "accepted_ts": ts,
    }


def _next_fr() -> dict:
    return {
        "repo": "SimonBarnett/a-search",
        "task": "FR",
        "id": "#4564",
        "seq": 2,
        "url": "https://github.com/SimonBarnett/bobiverse/issues/4564",
    }


def _write(home, *, accepted=None, unaccepted=None, done=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def test_fr4564_pass_on_github_closes_row_and_offers_next(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-100"
    _write(home, accepted=[_accepted_mrb(nick)], unaccepted=[_next_fr()])
    monkeypatch.setattr(
        gitclaim,
        "_lost_done_github_result",
        lambda row: str(row.get("url") or ""),
    )
    now = time.time()
    assert gitclaim.release_stale_busy(home, nick, now, session_started=now)
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert any(str(r.get("id")) == "#3614" for r in doc["done"])
    assert all(str(r.get("id")) != "#3614" for r in doc["unaccepted"])
    assert gitclaim.bored_gate(home, nick, "#marchhare", now + 1) != "busy"
    status, job = gitclaim.offer_focus_top(home, nick, "#marchhare", now=now + 2)
    assert status == "ok"
    assert job["id"] == "#4564"


def test_fr4564_requeue_not_offered_to_prior_holder(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-100"
    other = "marchhare-200"
    _write(home, accepted=[_accepted_mrb(nick)], unaccepted=[_next_fr()])
    monkeypatch.setattr(gitclaim, "_lost_done_github_result", lambda _row: None)
    now = time.time()
    assert gitclaim.release_stale_busy(home, nick, now, session_started=now)
    doc = gitclaim.load_queue(home)
    requeued = [r for r in doc["unaccepted"] if str(r.get("id")) == "#3614"]
    assert len(requeued) == 1
    assert requeued[0].get("prior_holder") == nick
    assert str(requeued[0].get("reconcile") or "").startswith("requeue:LOST_DONE_RESTART")
    status, job = gitclaim.offer_focus_top(home, nick, "#marchhare", now=now + 1)
    assert status == "ok"
    assert job["id"] == "#4564"
    status2, job2 = gitclaim.offer_focus_top(home, other, "#marchhare", now=now + 2)
    assert status2 == "ok"
    assert job2["id"] == "#3614"


def test_fr4564_unacked_reoffer_does_not_nak_busy(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-100"
    row = _accepted_mrb(nick)
    row.pop("nick", None)
    row.pop("accepted_by", None)
    row.pop("accepted_ts", None)
    row["offered_to"] = nick
    row["offered_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row["prior_holder"] = nick
    row["reconcile"] = "requeue:LOST_DONE_RESTART"
    nxt = _next_fr()
    _write(home, unaccepted=[row, nxt])
    gitclaim.note_seat_hold(home, nick, row)
    now = time.time()
    assert gitclaim.seat_open_job(home, nick, now) == ""
    assert gitclaim.bored_gate(home, nick, "#marchhare", now) != "busy"
    status, job = gitclaim.offer_focus_top(home, nick, "#marchhare", now=now + 1)
    assert status == "ok"
    assert job["id"] == "#4564"
