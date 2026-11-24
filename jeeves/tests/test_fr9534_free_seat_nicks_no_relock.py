"""FR #9534: free_seat_nicks must not re-enter load_queue / disk _lock under offer_top.

Tip build-jeeves hung in test_fr5201_copilot_timeout::test_timeout_returns_to_seats_without_redispatch
because offer_top held git-claim.lock then free_seat_nicks -> load_queue -> _lock spun on
time.sleep(0.02) until pytest-timeout.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import gitclaim
import jeeves_locks


REPO = "SimonBarnett/bobiverse"


@pytest.fixture(autouse=True)
def _disk_lock_only(monkeypatch):
    """Force the non-reentrant disk lock path (CI / tools without enable_inproc_locks)."""
    jeeves_locks.disable_inproc_locks()
    assert jeeves_locks.inproc_queue_lock() is None
    yield
    jeeves_locks.disable_inproc_locks()


def _queue_one_fr(home: Path, ident: str = "#9534") -> None:
    row = {
        "repo": REPO,
        "task": "FR",
        "id": ident,
        "title": "free_seat_nicks lock reentry",
        "url": f"https://github.com/{REPO}/issues/{ident.lstrip('#')}",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )


def test_fr9534_offer_top_under_disk_lock_completes_fast(tmp_path):
    """offer_top must finish well under LOCK_WAIT_S when only the disk lock exists."""
    home = tmp_path / "home"
    home.mkdir()
    _queue_one_fr(home)
    t0 = time.time()
    status, offered = gitclaim.offer_top(home, "ionos-123", "#ionos", now=time.time())
    dt = time.time() - t0
    assert status == "ok"
    assert offered and offered.get("id") == "#9534"
    # Pre-fix hung ~30s (full LOCK_WAIT_S). Budget leaves headroom for slow CI disks.
    assert dt < 5.0, f"offer_top took {dt:.2f}s — nested disk lock reentry?"


def test_fr9534_free_seat_nicks_doc_kw_under_held_lock(tmp_path):
    """Passing doc= while holding _lock must not attempt a second disk lock."""
    home = tmp_path / "home"
    home.mkdir()
    _queue_one_fr(home)
    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        t0 = time.time()
        free = gitclaim.free_seat_nicks(home, set(), doc=doc)
        dt = time.time() - t0
    assert isinstance(free, set)
    assert dt < 1.0, f"free_seat_nicks(doc=) under lock took {dt:.2f}s"


def test_fr9534_free_seat_nicks_without_doc_under_lock_times_out_fast(
    tmp_path, monkeypatch
):
    """Defense: pytest lock budget fails nested load_queue quickly (no doc=)."""
    monkeypatch.delenv("BOB_GITCLAIM_LOCK_S", raising=False)
    # Simulate pytest so _lock_wait_budget uses the 2s fail-fast path.
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr9534_nested")
    home = tmp_path / "home"
    home.mkdir()
    _queue_one_fr(home)
    with gitclaim._lock(home):
        t0 = time.time()
        # No doc= → load_queue waits then TimeoutError → empty accepted (busy=empty).
        free = gitclaim.free_seat_nicks(home, set())
        dt = time.time() - t0
    assert isinstance(free, set)
    assert dt < 5.0, f"nested load_queue under pytest budget took {dt:.2f}s (want ~2s)"
    assert dt >= 1.0, f"expected a short nested wait, got {dt:.2f}s"


def test_fr9534_lock_wait_budget_pytest_default(monkeypatch):
    monkeypatch.delenv("BOB_GITCLAIM_LOCK_S", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_fr9534_budget")
    assert gitclaim._lock_wait_budget(None) == 2.0
    assert gitclaim._lock_wait_budget(0.5) == 0.5
    assert gitclaim._lock_wait_budget(1.25) == 1.25
    monkeypatch.setenv("BOB_GITCLAIM_LOCK_S", "7")
    # Explicit env wins over pytest fail-fast (LOCK_WAIT_S was fixed at import).
    assert gitclaim._lock_wait_budget(None) == float(gitclaim.LOCK_WAIT_S)
