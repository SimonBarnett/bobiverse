"""FR #7966: unanswered offers become a per-seat refusal, not an infinite re-offer."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT = "redqueen-644"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["workers"] = {"644": {"state": "idle", "nick": SEAT}}
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _queue(home, row):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )


def _row():
    return {
        "repo": REPO,
        "task": "FIX",
        "id": "#7885",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/7885",
        "giveup_count": 0,
    }


def _offer(home, now):
    return gitclaim.offer_focus_top(home, SEAT, "#redqueen", now=now)


def test_fr7966_three_timeouts_refuse_the_seat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, _row())
    now = time.time()
    counts = []
    for i in range(gitclaim.OFFER_UNANSWERED_MAX):
        st, job = _offer(home, now)
        assert st == "ok" and job["offered_to"] == SEAT, (st, job)
        counts.append(int(job["offered_count"]))
        now += gitclaim.OFFER_TIMEOUT_S + 5
    assert counts == [1, 2, 3]
    # The next bored records the third timeout and does not offer this seat again.
    st2, job2 = _offer(home, now)
    assert st2 == "empty" and job2 is None
    final = gitclaim.load_unaccepted(home)[0]
    assert int(final["offered_count"]) == 3
    assert SEAT in final["offer_refused_by"]
    assert final.get("cooldown_until")
    assert float(final.get("no_eligible_since") or 0) > 0
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    outcomes = final.get("offer_outcomes") or []
    assert len([o for o in outcomes if o.get("outcome") == "timeout"]) == 3
    # A later bored does not climb offered_count.
    st3, _job3 = _offer(home, now + 10_000)
    assert st3 == "empty"
    again = gitclaim.load_unaccepted(home)[0]
    assert int(again["offered_count"]) == 3


def test_fr7966_nack_records_giveup_seat_and_reason(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = _row()
    row["nick"] = SEAT
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FIX",
        ident="#7885",
        now=time.time(),
        reason="worktree-absent",
    )
    assert st == "ok" and job is not None
    final = gitclaim.load_unaccepted(home)[0]
    assert SEAT.lower() in str(final.get("giveup_seats") or "").lower()
    assert final.get("giveup_reason") == "worktree-absent"
    outcomes = final.get("offer_outcomes") or []
    assert outcomes and outcomes[-1]["outcome"] == "nack"
    assert outcomes[-1]["reason"] == "worktree-absent"


def test_fr7966_other_live_seat_is_not_stamped_no_eligible(tmp_path, monkeypatch):
    """MRB #7972: no_eligible_since waits until every live seat is refused."""
    home = _home(tmp_path, monkeypatch)
    digest = bobreport.load_digest(home)
    digest["machines"]["redqueen"]["worker_list"] = [{"nick": SEAT, "state": "idle"}]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": "flamingo-1", "state": "idle"}]
    bobreport.save_digest(home, digest)
    _queue(home, _row())
    now = time.time()
    for _i in range(gitclaim.OFFER_UNANSWERED_MAX):
        st, job = _offer(home, now)
        assert st == "ok" and job["offered_to"] == SEAT
        now += gitclaim.OFFER_TIMEOUT_S + 5
    st2, job2 = _offer(home, now)
    assert st2 == "empty" and job2 is None
    held = gitclaim.load_unaccepted(home)[0]
    assert SEAT in held["offer_refused_by"]
    assert not held.get("no_eligible_since")
    st3, job3 = gitclaim.offer_focus_top(home, "flamingo-1", "#flamingo", now=now + 1)
    assert st3 == "ok" and job3["offered_to"] == "flamingo-1"
    offered = gitclaim.load_unaccepted(home)[0]
    assert not offered.get("no_eligible_since")


def test_fr7966_digest_snapshot_includes_offer_outcomes(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = _row()
    row["offer_refused_by"] = [SEAT]
    row["offer_outcomes"] = [{
        "seat": SEAT,
        "outcome": "timeout",
        "reason": "offer-timeout",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }]
    row["no_eligible_since"] = time.time() - timedelta(minutes=5).total_seconds()
    _queue(home, row)
    snap = bobreport._public_queue(home)
    shown = snap["unaccepted"][0]
    assert shown["offer_refused_by"] == [SEAT]
    assert shown["offer_outcomes"][0]["seat"] == SEAT
    assert float(shown["no_eligible_since"]) > 0
