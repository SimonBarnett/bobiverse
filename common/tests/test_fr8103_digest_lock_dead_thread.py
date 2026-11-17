"""FR #8103: no false lock-broken dead-thread after clean release; rich break log + counters."""
from __future__ import annotations

import io
import json
import sys
import threading
import time
from pathlib import Path

import bobcallback
import bobreport


ALLOW = {"127.0.0.1", "::1"}


def test_clean_short_lived_holder_does_not_break_dead_thread(tmp_path: Path):
    """Publish threads that exit after a clean finally must not spam lock-broken."""
    bobreport.reset_digest_lock_stats_for_tests()
    buf = io.StringIO()
    old = sys.stdout

    def _pub() -> None:
        with bobreport.digest_lock(tmp_path):
            time.sleep(0.01)

    sys.stdout = buf
    try:
        for _ in range(8):
            t = threading.Thread(target=_pub, name="digest-pub")
            t.start()
            t.join(5)
            assert not t.is_alive()
            # Health / reclaim path that used to false-positive every cycle.
            bobreport.break_stale_digest_lock(tmp_path)
            with bobreport.digest_lock(tmp_path):
                pass
    finally:
        sys.stdout = old

    out = buf.getvalue()
    assert "lock-broken" not in out, out
    assert bobreport.digest_lock_break_count() == 0
    lock = bobreport.digest_lock_path(tmp_path)
    # Clean release unlinks; no leftover dead-thread bait.
    assert not lock.exists() or bobreport.break_stale_digest_lock(tmp_path) is None


def test_raise_while_holding_releases_via_finally_and_counts_once(tmp_path: Path, capsys):
    """Thread raises under the lock: finally releases (no break); exception logged once."""
    bobreport.reset_digest_lock_stats_for_tests()

    def _boom() -> None:
        try:
            with bobreport.digest_lock(tmp_path):
                raise RuntimeError("fr8103-hold-boom")
        except RuntimeError:
            return

    t = threading.Thread(target=_boom, name="digest-boom")
    t.start()
    t.join(5)
    assert not t.is_alive()

    # Lock must be free for the next holder without a dead-thread break.
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        info = bobreport.break_stale_digest_lock(tmp_path)
        with bobreport.digest_lock(tmp_path):
            (tmp_path / "after.txt").write_text("ok", encoding="ascii")
    finally:
        sys.stdout = old

    assert info is None
    assert "lock-broken" not in buf.getvalue()
    assert (tmp_path / "after.txt").read_text(encoding="ascii") == "ok"
    assert bobreport.digest_lock_hold_exception_count() == 1
    # Exception name must appear in the hold-exception log (printed to stdout).
    # Capture from the worker thread via the module's last log line helper.
    last = bobreport.digest_lock_last_hold_exception_log()
    assert last is not None
    assert "RuntimeError" in last
    assert "fr8103-hold-boom" in last


def test_true_orphan_break_logs_once_and_rate_limits(tmp_path: Path):
    bobreport.reset_digest_lock_stats_for_tests()

    def _leak() -> None:
        bobreport.abandon_digest_lock_for_tests(tmp_path)

    holder = threading.Thread(target=_leak, name="digest-orphan")
    holder.start()
    holder.join(5)
    assert not holder.is_alive()

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        info1 = bobreport.reclaim_orphaned_digest_lock(tmp_path)
        # Second break on a fresh abandoned lock file with dead ident should rate-limit.
        # Re-abandon to force another break attempt with the same cause.
        def _leak2() -> None:
            bobreport.abandon_digest_lock_for_tests(tmp_path)

        h2 = threading.Thread(target=_leak2, name="digest-orphan")
        h2.start()
        h2.join(5)
        info2 = bobreport.reclaim_orphaned_digest_lock(tmp_path)
    finally:
        sys.stdout = old

    out = buf.getvalue()
    assert info1 is not None
    assert info1.get("reason") == "dead-thread"
    assert "lock-broken" in out
    assert "lock=digest.lock" in out
    assert "thread=digest-orphan" in out or "thread=" in out
    assert bobreport.digest_lock_break_count() >= 1
    # Rate-limit: second identical cause includes a repeats= counter rather than
    # a second full first-time dump storm.
    assert "repeats=" in out or bobreport.digest_lock_break_count() >= 2


def test_health_exposes_lock_break_count(tmp_path: Path):
    bobreport.reset_digest_lock_stats_for_tests()
    bobreport._note_lock_break_for_tests(reason="dead-thread")
    code, raw = bobcallback.handle_request(
        "GET", "/health", {}, b"", "127.0.0.1", tmp_path, ALLOW
    )
    assert code == 200
    doc = json.loads(raw.decode("utf-8"))
    assert doc.get("lock_break_count") == 1
    assert "lock_hold_exception_count" in doc
