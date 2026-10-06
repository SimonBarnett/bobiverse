"""FR #2729: the report-path MRB purge must never hold the queue lock across GitHub calls.

Jeeves wedged on ionos (2026-10-06): every GET /bob/v1/report ran
``purge_dead_mrb_rows`` with a fresh ``cache={}`` and did one serial GitHub GET per
open MRB row *inside* ``gitclaim._lock``. With ~8-10 open MRB rows, trays/ears polled
faster than the purge finished, so ``!bored`` / ``load_queue`` / ``offer_focus_top``
starved behind the in-proc RLock.
"""
from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import pytest

import bobreport
import gitclaim
import jeeves_locks


REPO = "SimonBarnett/bobiverse"


@pytest.fixture(autouse=True)
def _prod_locks(monkeypatch, tmp_path):
    """Mirror jeeves.exe: in-proc RLock for the queue (FR #1993), isolated digest home."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    jeeves_locks.disable_inproc_locks()
    jeeves_locks.enable_inproc_locks()
    cache = getattr(gitclaim, "PR_EXISTS_SHARED_CACHE", None)
    if cache is not None:
        cache.clear()
    yield
    jeeves_locks.disable_inproc_locks()
    if cache is not None:
        cache.clear()


def _mrb(num: int) -> dict:
    return {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": num,
        "ts": "t",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }


def _queue(home: Path, rows) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(rows), "accepted": [], "done": []},
    )


def _ids(home: Path) -> set[str]:
    doc = gitclaim._load_queue_unlocked(home)
    return {gitclaim._norm_row_id(r.get("id")) for r in doc.get("unaccepted") or []}


def _lock_free_from_other_thread(home: Path, wait: float = 0.5) -> bool:
    got: list[bool] = []

    def _try():
        lk = jeeves_locks.inproc_queue_lock()
        ok = lk.acquire(timeout=wait)
        if ok:
            lk.release()
        got.append(ok)

    t = threading.Thread(target=_try, daemon=True)
    t.start()
    t.join(wait + 1.0)
    return bool(got and got[0])


def test_fr2729_pr_exists_runs_with_queue_lock_free(tmp_path):
    _queue(tmp_path, [_mrb(1), _mrb(2), _mrb(3)])
    seen: list[bool] = []

    def pr_exists(repo, num):
        seen.append(_lock_free_from_other_thread(tmp_path))
        return str(num) != "2"

    gitclaim.purge_dead_mrb_rows(tmp_path, pr_exists=pr_exists)
    assert seen, "pr_exists was never consulted"
    assert all(seen), "GitHub check ran while the queue lock was held (FR #2729)"
    assert _ids(tmp_path) == {"#1", "#3"}, "dead MRB row must still be purged"


def test_fr2729_ten_plus_open_mrb_rows_slow_github_do_not_starve_queue(tmp_path, monkeypatch):
    """12 open MRB rows, GitHub 0.25 s per call, 6 concurrent report GETs.

    On main the first purge holds the queue lock for ~3 s and every other GET adds
    another ~3 s, so a chair ``load_queue`` (the !bored path) waits many seconds.
    """
    n_rows = 12
    _queue(tmp_path, [_mrb(100 + i) for i in range(n_rows)])
    calls: list[str] = []
    calls_mu = threading.Lock()

    def slow_checker(home=None, cache=None):
        def _check(repo, num):
            with calls_mu:
                calls.append(f"{repo}#{num}")
            time.sleep(0.25)
            return True

        return _check

    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", slow_checker)

    readers = [threading.Thread(target=bobreport._public_queue, args=(tmp_path,), daemon=True) for _ in range(6)]
    for t in readers:
        t.start()
    time.sleep(0.3)  # let the first purge get into its GitHub calls
    t0 = time.monotonic()
    doc = gitclaim.load_queue(tmp_path)
    waited = time.monotonic() - t0
    for t in readers:
        t.join(15)
    assert len(doc.get("unaccepted") or []) == n_rows
    assert waited < 0.5, f"load_queue waited {waited:.2f}s behind the report purge (FR #2729)"
    assert not any(t.is_alive() for t in readers)
    # single-flight: concurrent GETs do not each re-ask GitHub for every row
    assert len(calls) <= n_rows, f"{len(calls)} GitHub calls for {n_rows} rows"


def test_fr2729_report_uses_shared_60s_cache(tmp_path, monkeypatch):
    """Two report GETs inside 60 s must not repeat the per-PR GitHub calls."""
    _queue(tmp_path, [_mrb(200 + i) for i in range(10)])
    import gh_filer

    monkeypatch.setattr(gh_filer, "ensure_gh_token_env", lambda *a, **k: "env")
    monkeypatch.setenv("GH_TOKEN", "test-token-not-real")
    hits: list[str] = []

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        hits.append(req.full_url)
        return _Resp(json.dumps({"state": "open"}).encode())

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", fake_urlopen)
    bobreport._public_queue(tmp_path)
    first = len(hits)
    bobreport._public_queue(tmp_path)
    assert first == 10
    assert len(hits) == first, "second report GET re-asked GitHub (no shared cache)"
    assert gitclaim.PR_EXISTS_CACHE_TTL_S == 60.0


def test_fr2729_ttl_cache_expires():
    now = [1000.0]
    c = gitclaim.TTLCache(60.0, clock=lambda: now[0])
    c["a"] = True
    assert c.get("a") is True and "a" in c
    now[0] += 59.0
    assert c["a"] is True
    now[0] += 2.0
    assert "a" not in c and c.get("a", "miss") == "miss"


def test_fr2729_purge_skips_when_lock_not_free_quickly(tmp_path):
    _queue(tmp_path, [_mrb(5)])
    asked: list[str] = []
    holding = threading.Event()
    release = threading.Event()

    def _holder():
        with gitclaim._lock(tmp_path):
            holding.set()
            release.wait(5)

    th = threading.Thread(target=_holder, daemon=True)
    th.start()
    assert holding.wait(2)
    try:
        t0 = time.monotonic()
        n = gitclaim.purge_dead_mrb_rows(
            tmp_path, pr_exists=lambda r, n: asked.append(n) or False, lock_timeout=0.2
        )
        took = time.monotonic() - t0
    finally:
        release.set()
        th.join(5)
    assert n == 0 and not asked
    assert took < 1.0
    assert _ids(tmp_path) == {"#5"}


def test_fr2729_report_purge_uses_short_lock_wait(tmp_path, monkeypatch):
    _queue(tmp_path, [])
    seen: dict = {}

    def fake_purge(home, **kw):
        seen.update(kw)
        return 0

    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", lambda **k: (lambda r, n: True))
    monkeypatch.setattr(gitclaim, "purge_dead_mrb_rows", fake_purge)
    bobreport._public_queue(tmp_path)
    assert 0 < float(seen.get("lock_timeout") or 0) <= 0.5


def test_fr2729_row_added_during_github_check_is_not_lost(tmp_path):
    """Re-lock + reload: a row queued while GitHub was being asked survives the purge."""
    _queue(tmp_path, [_mrb(10), _mrb(11)])
    added = []

    def pr_exists(repo, num):
        if not added:
            added.append(True)
            with gitclaim._lock(tmp_path):
                doc = gitclaim._load_queue_unlocked(tmp_path)
                doc["unaccepted"].append(_mrb(12))
                gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
        return str(num) != "10"

    gitclaim.purge_dead_mrb_rows(tmp_path, pr_exists=pr_exists)
    assert _ids(tmp_path) == {"#11", "#12"}
