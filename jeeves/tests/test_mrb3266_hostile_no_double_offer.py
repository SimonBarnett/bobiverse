"""Hostile MRB #3266 gates for FR #3192 (no double-offer).

Vision (bob/VISION.md S4): program posts !bored; agent ACK/DONE only — a seat must
not be handed a second job while still holding an undelivered/unacked assign.
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "url": kw.pop("url", f"https://github.com/{repo}/issues/{num}"),
    }
    r.update(kw)
    return r


def _queue(home: Path, rows: list) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def test_mrb3266_clear_seat_offer_unstamps_just_pinned_row(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 7, 1), _row("o/a", "FR", 8, 2)])
    t0 = time.time()
    st, job = gitclaim.offer_focus_top(home, "marchhare-50", "#marchhare", now=t0)
    assert st == "ok" and job is not None
    assert job.get("offered_to") == "marchhare-50"
    assert gitclaim.clear_seat_offer(home, "marchhare-50", job) is True
    rows = gitclaim.load_unaccepted(home)
    pinned = [r for r in rows if r["id"] == job["id"]][0]
    assert not pinned.get("offered_to")
    # Seat is free again; another seat can take the same row.
    st2, job2 = gitclaim.offer_focus_top(home, "marchhare-60", "#marchhare", now=t0 + 1)
    assert st2 == "ok" and job2["id"] == job["id"]
    assert job2.get("offered_to") == "marchhare-60"


def test_mrb3266_should_drop_stale_bored_except_just_stamped(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 3, 1)])
    t0 = time.time()
    st, job = gitclaim.offer_focus_top(home, "marchhare-9", "#marchhare", now=t0)
    assert st == "ok" and job is not None
    # Just-stamped row must not look like a pre-existing pending offer.
    assert gitclaim.should_drop_stale_bored(home, "marchhare-9", t0 + 1, except_job=job) is False
    # Without except_job, the live pin counts as pending → drop.
    assert gitclaim.should_drop_stale_bored(home, "marchhare-9", t0 + 1) is True


def test_mrb3266_offer_focus_top_holding_live_returns_empty(tmp_path, monkeypatch):
    """Defense path: calling offer_focus_top while holding live offered_to returns empty."""
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("o/a", "FR", 1, 1), _row("o/a", "FR", 2, 2)])
    t0 = time.time()
    st1, j1 = gitclaim.offer_focus_top(home, "marchhare-100", "#marchhare", now=t0)
    assert st1 == "ok" and j1 is not None
    st2, j2 = gitclaim.offer_focus_top(home, "marchhare-100", "#marchhare", now=t0 + 2)
    assert st2 == "empty" and j2 is None
    # First pin still owned by this seat.
    left = [r for r in gitclaim.load_unaccepted(home) if r.get("offered_to") == "marchhare-100"]
    assert len(left) == 1 and left[0]["id"] == j1["id"]


def test_mrb3266_helpers_and_wiring_present():
    assert callable(gitclaim.seat_pending_offer)
    assert callable(gitclaim.should_drop_stale_bored)
    assert callable(gitclaim.clear_seat_offer)
    root = Path(__file__).resolve().parents[2]
    worker = (root / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "def has_pending_work" in worker
    assert "FR #3192" in worker
    irc = (root / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "should_drop_stale_bored" in irc
    assert "clear_seat_offer" in irc
