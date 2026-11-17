"""FR #8017: deterministic NACK before ACK must cool that seat for the same job."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT_A = "flamingo-18988"
SEAT_B = "flamingo-20001"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": SEAT_A, "state": "idle"},
        {"nick": SEAT_B, "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _row(**kw):
    r = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8006",
        "seq": 1,
        "ts": "2026-11-17T13:36:00Z",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/8006",
        "title": "MRB 8006",
        "giveup_count": 0,
    }
    r.update(kw)
    return r


def test_deterministic_nack_reason_classes():
    assert gitclaim.is_deterministic_nack_reason(
        "worktree-create-failed:git-worktree (FR #6240)"
    )
    assert gitclaim.is_deterministic_nack_reason("worktree-absent")
    assert gitclaim.is_deterministic_nack_reason("job-context-malformed (FR #6240)")
    assert gitclaim.is_deterministic_nack_reason("job-context-ambiguous")
    assert not gitclaim.is_deterministic_nack_reason("busy")
    assert not gitclaim.is_deterministic_nack_reason("out-of-fuel")
    assert not gitclaim.is_deterministic_nack_reason("")


def test_preack_deterministic_nack_blocks_same_seat_allows_other(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(offered_to=SEAT_A, offered_ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    result = shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#flamingo",
        body=f"NACK MRB {REPO}#8006 worktree-create-failed:git-worktree (FR #6240)",
        post_fn=lambda _p: 204,
    )
    assert result.get("handled")
    assert result.get("status") == "missing"
    held = gitclaim.load_unaccepted(home)[0]
    stamps = held.get("deterministic_nack_until") or {}
    assert any(
        (gitclaim.canonical_worker_nick(k) or k).lower() == SEAT_A.lower()
        for k in stamps
    )
    assert held.get("giveup_reason", "").startswith("worktree-create-failed")
    assert not held.get("offered_to")
    assert int(held.get("giveup_count") or 0) == 0
    assert not held.get("needs_human")
    assert not held.get("giveup_seats")

    st_a, job_a = gitclaim.offer_focus_top(home, SEAT_A, "#flamingo", now=now + 10)
    assert st_a == "empty" and job_a is None

    st_b, job_b = gitclaim.offer_focus_top(home, SEAT_B, "#flamingo", now=now + 10)
    assert st_b == "ok" and job_b is not None
    assert job_b["offered_to"] == SEAT_B


def test_preack_deterministic_nack_allows_same_seat_after_cooldown(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(offered_to=SEAT_A)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#flamingo",
        body=f"NACK MRB {REPO}#8006 worktree-create-failed:git-worktree (FR #6240)",
        post_fn=lambda _p: 204,
    )
    held = gitclaim.load_unaccepted(home)[0]
    assert held.get("deterministic_nack_until")
    assert gitclaim.offer_focus_top(home, SEAT_A, "#flamingo", now=now + 10)[0] == "empty"
    later = now + float(gitclaim.GIVEUP_COOLDOWN_S) + 5
    st, job = gitclaim.offer_focus_top(home, SEAT_A, "#flamingo", now=later)
    assert st == "ok" and job is not None
    assert job["offered_to"] == SEAT_A


def test_transient_preack_nack_does_not_stamp_cooldown(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    now = time.time()
    row = _row(offered_to=SEAT_A)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    shop_listen.handle_shop_worker_line(
        home,
        nick=SEAT_A,
        channel="#flamingo",
        body=f"NACK MRB {REPO}#8006 busy try later",
        post_fn=lambda _p: 204,
    )
    held = gitclaim.load_unaccepted(home)[0]
    assert not held.get("deterministic_nack_until")
    st, job = gitclaim.offer_focus_top(home, SEAT_A, "#flamingo", now=now + 10)
    assert st == "ok" and job is not None
