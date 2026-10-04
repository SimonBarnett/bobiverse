"""FR #1811: git-claim.lock timeout/OSError must not silently drop queue events."""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path
from unittest import mock

import gitclaim


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "digest"
    h.mkdir(parents=True, exist_ok=True)
    return h


def _fr(n: int) -> gitclaim.GitClaim:
    return gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id=f"#{n}",
        event="issues",
        action="opened",
        line=f"GIT issues opened #{n}",
        title=f"feature request {n}",
        body="implement me",
        labels=("feature-request",),
        state="open",
    )


def test_fr1811_lock_timeout_spools_and_distinguishes_err(tmp_path: Path):
    home = _home(tmp_path)
    claim = _fr(1811)

    @contextlib.contextmanager
    def boom(_home):
        raise TimeoutError("git-claim lock")
        yield  # pragma: no cover

    with mock.patch.object(gitclaim, "_lock", boom):
        result = gitclaim.apply_queue_event(home, claim)
    assert result == "error:queue-lock-timeout"
    pending = gitclaim.pending_path(home)
    assert pending.exists()
    body = pending.read_text(encoding="utf-8")
    assert "#1811" in body
    with mock.patch.object(gitclaim, "_lock", boom):
        assert gitclaim.enqueue_unaccepted(home, claim) == "error:queue-lock-timeout"


def test_fr1811_drain_pending_on_next_lock(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._spool_pending(home, _fr(9001))
    gitclaim._spool_pending(home, _fr(9002))
    result = gitclaim.apply_queue_event(home, _fr(9003))
    assert result == "added"
    doc = gitclaim.load_queue(home)
    ids = {r["id"] for r in doc["unaccepted"]}
    assert {"#9001", "#9002", "#9003"} <= ids
    assert not gitclaim.pending_path(home).exists()


def test_fr1811_noop_skips_rewrite(tmp_path: Path):
    home = _home(tmp_path)
    c = _fr(42)
    assert gitclaim.apply_queue_event(home, c) == "added"
    qpath = gitclaim.queue_path(home)
    mtime1 = qpath.stat().st_mtime_ns
    time.sleep(0.05)
    result = gitclaim.apply_queue_event(home, c)
    assert result in ("duplicate", "noop")
    if result == "noop":
        assert qpath.stat().st_mtime_ns == mtime1


def test_fr1811_write_retries_permission_error(tmp_path: Path):
    home = _home(tmp_path)
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("simulated AV lock")
        return real_replace(src, dst)

    with mock.patch.object(os, "replace", flaky):
        assert gitclaim.apply_queue_event(home, _fr(77)) == "added"
    assert calls["n"] >= 3
    assert any(r["id"] == "#77" for r in gitclaim.load_queue(home)["unaccepted"])


def test_fr1811_bobreport_maps_specific_err(tmp_path: Path):
    import bobreport

    home = _home(tmp_path)

    def fake_enqueue(_home, _claim):
        return "error:queue-lock-timeout"

    payload = {
        "action": "opened",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 1,
            "title": "feature request one",
            "body": "body",
            "state": "open",
            "labels": [{"name": "feature-request"}],
        },
    }
    with mock.patch.object(gitclaim, "enqueue_unaccepted", fake_enqueue):
        with mock.patch.object(
            bobreport,
            "enqueue_chair_fleet_privmsg",
            return_value=True,
        ):
            # use real claim_from_payload so announce line builds
            out = bobreport.apply_git_webhook(home, "issues", payload)
    assert out.ok is False
    assert out.err == "queue-lock-timeout"


def test_fr1811_concurrent_applies_lose_no_rows(tmp_path: Path):
    home = _home(tmp_path)
    n = 40

    def worker(i: int) -> None:
        gitclaim.apply_queue_event(home, _fr(1000 + i))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Drain residual pending under lock until empty.
    for _ in range(10):
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            pending = gitclaim._pop_all_pending(home)
            if not pending:
                break
            dirty = False
            for item in pending:
                ch = gitclaim._apply_claim_to_doc(doc, item)
                if ch not in ("noop", "error"):
                    dirty = True
                elif ch == "error":
                    gitclaim._spool_pending(home, item)
            if dirty:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)

    doc = gitclaim.load_queue(home)
    ids = {r["id"] for r in doc["unaccepted"]}
    pending_ids: set[str] = set()
    pp = gitclaim.pending_path(home)
    if pp.exists():
        for line in pp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pending_ids.add(str(json.loads(line).get("id") or ""))
    missing = [
        f"#{1000 + i}"
        for i in range(n)
        if f"#{1000 + i}" not in ids and f"#{1000 + i}" not in pending_ids
    ]
    assert not missing, missing
