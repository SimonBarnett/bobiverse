"""FR #8924: an offer-timeout refusal expires after cooldown and can be re-offered."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"
SEAT = "marchhare-4208"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "4208": {"state": "idle", "nick": SEAT, "jobs": []}
    }
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": SEAT, "state": "idle", "jobs": []}
    ]
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
        "id": "#8794",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/8794",
        "giveup_count": 0,
    }


def _burn(home, now):
    for _i in range(gitclaim.OFFER_UNANSWERED_MAX):
        st, job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=now)
        assert st == "ok" and job["offered_to"] == SEAT
        now += gitclaim.OFFER_TIMEOUT_S + 5
    st, job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=now)
    assert st == "empty" and job is None
    return now


def test_fr8924_timeout_reason_and_reoffer_after_cooldown(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, _row())
    now = _burn(home, time.time())
    held = gitclaim.load_unaccepted(home)[0]
    assert SEAT in held["offer_refused_by"]
    reasons = [o.get("reason") for o in held["offer_outcomes"]]
    assert "offer-timeout:idle-no-ack" in reasons
    st, _job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=now + 30)
    assert st == "empty"
    later = now + gitclaim.GIVEUP_COOLDOWN_S + 5
    st2, job2 = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=later)
    assert st2 == "ok" and job2["offered_to"] == SEAT
    again = gitclaim.load_unaccepted(home)[0]
    assert SEAT not in (again.get("offer_refused_by") or [])
    assert int(again.get("offer_refusal_waves") or 0) == 1
    assert any(o.get("reason") == "offer-timeout-expired" for o in again["offer_outcomes"])


def test_fr8924_second_expiry_escalates_once(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, _row())
    now = _burn(home, time.time())
    later = now + gitclaim.GIVEUP_COOLDOWN_S + 5
    st, job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=later)
    assert st == "ok" and job["offered_to"] == SEAT
    # That re-offer is silence 1 of the next wave once it ages. Two further
    # offers then the third silence refuses the seat again.
    now2 = later
    for _i in range(gitclaim.OFFER_UNANSWERED_MAX - 1):
        now2 += gitclaim.OFFER_TIMEOUT_S + 5
        st, job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=now2)
        assert st == "ok" and job["offered_to"] == SEAT
    now2 += gitclaim.OFFER_TIMEOUT_S + 5
    st, job = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=now2)
    assert st == "empty" and job is None
    cap_at = now2 + gitclaim.GIVEUP_COOLDOWN_S + 5
    st2, job2 = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=cap_at)
    assert st2 == "empty" and job2 is None
    final = gitclaim.load_unaccepted(home)[0]
    assert final.get("offer_escalate_reason") == "offer-timeout-cap"
    assert SEAT in final["offer_refused_by"]
    st3, _job3 = gitclaim.offer_focus_top(home, SEAT, "#marchhare", now=cap_at + 10)
    assert st3 == "empty"
