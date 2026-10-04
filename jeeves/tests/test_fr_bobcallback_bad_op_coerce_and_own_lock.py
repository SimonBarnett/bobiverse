"""BobCallback: coerce legacy report POSTs; never break own live stale lock."""
from __future__ import annotations

import os
import time
from pathlib import Path

import bobcallback
import bobreport


def test_coerce_legacy_pcent_and_working_on_without_op():
    p = bobcallback.coerce_report_payload(
        {"machine": "win-mpre8vi4u6u", "pcent": {"grok-chat": 50}}
    )
    assert p["op"] == "merge"

    p2 = bobcallback.coerce_report_payload(
        {
            "machine": "win-mpre8vi4u6u",
            "pid": 15656,
            "working_on": "bobiverse UAT #0",
        }
    )
    assert p2["op"] == "merge"

    p3 = bobcallback.coerce_report_payload(
        {
            "machine": "win-mpre8vi4u6u",
            "nick": "win-mpre8vi4u6u-15656",
            "pid": "15656",
            "working_on": "x",
        }
    )
    assert p3["op"] == "worker-work"
    assert p3["state"] == "doing"
    assert p3["work"] == "x"


def test_coerce_underscore_aliases():
    p = bobcallback.coerce_report_payload(
        {
            "op": "worker_upsert",
            "machine": "marchhare",
            "nick": "marchhare-1",
            "pid": "1",
        }
    )
    assert p["op"] == "worker-upsert"


def test_break_stale_skips_own_live_pid_even_when_mtime_old(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "5")
    home = tmp_path
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    me = os.getpid()
    lock.write_text(f"{me}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is None, f"must not break own live lock: {info}"
    assert lock.exists()


def test_break_stale_still_breaks_foreign_old_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "5")
    home = tmp_path
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    # Unlikely-to-be-alive PID
    lock.write_text("1\n0\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is not None
    assert info["reason"] in ("stale", "dead-pid")
    assert not lock.exists()
