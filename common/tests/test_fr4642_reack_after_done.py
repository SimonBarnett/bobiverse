"""FR #4642: re-ACK after DONE must not re-hold; a lost follow-up DONE must not pin !bored."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    monkeypatch.setattr(gitclaim, "_lost_done_github_result", lambda row: None)
    return tmp_path


def _done(home, nick="marchhare-13128"):
    gitclaim.ledger_note_event(
        home, nick, "DONE", "FIX", "SimonBarnett/a-search", "#3359",
        result="PASS", url="https://github.com/SimonBarnett/a-search/pull/3359",
    )


def _ack(home, nick="marchhare-13128"):
    return shop_listen.handle_shop_worker_line(
        home,
        nick=nick,
        channel="#marchhare",
        body="ACK FIX SimonBarnett/a-search#3359",
        post_fn=lambda _p: 204,
    )


def test_reack_after_done_does_not_hold(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-13128"
    _done(home, nick)
    out = _ack(home, nick)
    assert out["status"] == "duplicate-after-done"
    assert gitclaim.seat_open_job(home, nick) == ""


def test_reoffer_after_done_allows_ack_hold(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-13128"
    _done(home, nick)
    time.sleep(0.01)
    assert gitclaim.note_seat_hold(
        home, nick,
        {"repo": "SimonBarnett/a-search", "task": "FIX", "id": "#3359"},
        via="offer",
    )
    out = _ack(home, nick)
    assert out["status"] == "missing"
    assert "held FIX" in gitclaim.seat_open_job(home, nick)


def test_bored_clears_hold_when_done_ledger_says_finished(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "marchhare-13128"
    gitclaim.note_seat_hold(
        home, nick,
        {"repo": "SimonBarnett/a-search", "task": "FIX", "id": "#3359"},
        via="ack-missing",
    )
    assert "held FIX" in gitclaim.seat_open_job(home, nick)
    time.sleep(0.01)
    _done(home, nick)
    now = time.time()
    assert gitclaim.bored_gate(home, nick, "#marchhare", now) == "ok"
    assert gitclaim.seat_open_job(home, nick) == ""
    freed = gitclaim.release_duplicate_done_hold(home, nick)
    assert freed == ""
