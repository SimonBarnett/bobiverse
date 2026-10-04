"""FR #1993 / #2309: sticky same-seat rebroadcast must not refresh offered_ts forever."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"ionos", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{seq:02d}Z",
        "line": "x",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []}
    )


def test_same_seat_rebroadcast_preserves_offered_ts_and_increments_count(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1)])
    t0 = time.time()
    st1, j1 = gitclaim.offer_focus_top(
        _home, "win-mpre8vi4u6u-1", "#win-mpre8vi4u6u", now=t0
    )
    assert st1 == "ok" and j1["offered_count"] == 1
    ts1 = j1["offered_ts"]
    st2, j2 = gitclaim.offer_focus_top(
        _home, "win-mpre8vi4u6u-1", "#win-mpre8vi4u6u", now=t0 + 10
    )
    assert st2 == "ok" and j2["id"] == "#1"
    assert j2["offered_ts"] == ts1, "rebroadcast must not refresh offered_ts"
    assert j2["offered_count"] == 2


def test_sticky_count_clears_offer_so_other_seat_can_take(_home):
    _queue(
        _home,
        [_row("o/a", "FR", 9, 1)],
    )
    t0 = time.time()
    nick = "win-mpre8vi4u6u-1"
    st, job = gitclaim.offer_focus_top(_home, nick, "#win-mpre8vi4u6u", now=t0)
    assert st == "ok"
    rows = gitclaim.load_unaccepted(_home)
    rows[0]["offered_count"] = gitclaim.STICKY_OFFER_MAX
    rows[0]["offered_to"] = nick
    rows[0]["offered_ts"] = job["offered_ts"]
    _queue(_home, rows)
    st2, job2 = gitclaim.offer_focus_top(
        _home, "win-mpre8vi4u6u-2", "#win-mpre8vi4u6u", now=t0 + 1
    )
    assert st2 == "ok" and job2["id"] == "#9"
    assert job2["offered_to"] == "win-mpre8vi4u6u-2"
    assert job2.get("offered_count") == 1


def test_offer_timeout_still_clears_without_ts_refresh(_home):
    _queue(_home, [_row("o/a", "FR", 1, 1), _row("o/b", "FR", 2, 2)])
    t0 = time.time()
    s1, j1 = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", now=t0)
    assert s1 == "ok" and j1["id"] == "#1"
    s2, j2 = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos", now=t0 + 5)
    assert j2["id"] == "#1" and j2["offered_ts"] == j1["offered_ts"]
    s3, j3 = gitclaim.offer_focus_top(
        _home, "ionos-3", "#ionos", now=t0 + gitclaim.OFFER_TIMEOUT_S + 1
    )
    assert s3 == "ok" and j3["id"] == "#1"
    assert j3["offered_to"] == "ionos-3"
