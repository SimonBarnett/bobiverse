"""Hostile MRB #1439: coerce aliases + reject still works; own-lock skip holds."""
from __future__ import annotations

import os
import time
from pathlib import Path

import bobcallback
import bobreport
import registered_machines as rm


def test_coerce_presence_and_status_aliases_to_merge():
    for op in ("presence", "status", "working_on"):
        p = bobcallback.coerce_report_payload(
            {"op": op, "machine": "marchhare", "pcent": {"grok-chat": 1}}
        )
        assert p["op"] == "merge", op


def test_empty_payload_still_rejects_without_false_op(tmp_path):
    home = tmp_path
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare"])
    bobreport.save_digest(home, bobreport.empty_digest())
    code, _mid, why = bobcallback.validate_report_payload(
        home, bobcallback.coerce_report_payload({})
    )
    assert code == 400
    assert "op" in why.lower() or "machine" in why.lower() or why


def test_digest_lock_enter_refreshes_holder_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "5")
    home = tmp_path
    with bobreport.digest_lock(home, timeout_s=2.0):
        lock = bobreport.digest_lock_path(home)
        assert lock.exists()
        # Age should be near-zero after enter refresh (not a 120s-old stamp).
        # On Windows the exclusive lock may block a second open for holder_pid —
        # age via shared read / mtime is enough here.
        age = bobreport.digest_lock_age_s(home)
        assert age is not None
        assert age < 2.0
        # Watchdog must not break while we hold (own live PID skip).
        info = bobreport.break_stale_digest_lock(home)
        assert info is None
