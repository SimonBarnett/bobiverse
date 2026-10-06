"""FR #2902: own-live digest.lock past stale is healthy; watchdog logs honestly."""
from __future__ import annotations

import io
import json
import os
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import bobcallback
import bobreport
import registered_machines as rm


ALLOW = {"127.0.0.1", "::1"}


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    return tmp_path


def test_health_ok_when_own_live_lock_past_stale(home, monkeypatch):
    """Own PID holding digest.lock older than lock_stale_s must still /health 200."""
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "2")
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    me = os.getpid()
    lock.write_text(f"{me}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))

    code, raw = bobcallback.handle_health_get(home)
    doc = json.loads(raw.decode("utf-8"))
    assert code == 200, doc
    assert doc.get("ok") is True
    assert doc.get("lock_pid") == me
    assert doc.get("pid") == me
    assert doc.get("lock_own") is True
    assert float(doc.get("lock_age_s") or 0) >= 2.0
    assert lock.exists(), "own live lock must remain"


def test_watchdog_try_break_left_own_live_no_false_broke(home, monkeypatch, capsys):
    """Watchdog must not claim it broke a lock it left for own live pid."""
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "2")
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    me = os.getpid()
    lock.write_text(f"{me}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))

    bobcallback._watchdog_try_break(home, why="err=HTTP Error 503: Service Unavailable")
    out = capsys.readouterr().out
    assert "broke digest.lock" not in out
    assert "left own live digest.lock" in out
    assert f"pid={me}" in out
    assert lock.exists()


def test_watchdog_try_break_logs_info_when_actually_broke(home, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "2")
    lock = bobreport.digest_lock_path(home)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("1\n0\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))

    bobcallback._watchdog_try_break(home, why="not-ok")
    out = capsys.readouterr().out
    assert "INFO health-watchdog broke digest.lock" in out
    assert not lock.exists()


def test_git_claim_does_not_hold_digest_lock(home, monkeypatch):
    """claim_top slow wait must not run while digest.lock is held (FR #2902 root cause)."""
    held = {"during": False}

    def slow_claim(h, nick, channel):
        held["during"] = bobreport.digest_lock_path(h).exists() and (
            bobreport.digest_lock_holder_pid(h) == os.getpid()
        )
        # Also check re-entrancy depth / thread lock via trying a non-blocking sense:
        # if apply_callback still wrapped claim in @_digest_locked, depth would be > 0.
        depth = getattr(bobreport._LOCK_STATE, "depth", 0)
        held["depth"] = depth
        time.sleep(0.05)
        return "ok", None

    monkeypatch.setattr("gitclaim.claim_top", slow_claim)
    out = bobreport.apply_callback(
        home, {"op": "git-claim", "nick": "marchhare-1", "channel": "#marchhare"}
    )
    assert out.ok is True
    assert held["depth"] == 0, f"git-claim must not run under digest.lock depth={held['depth']}"


def test_merge_still_uses_digest_lock(home, monkeypatch):
    seen = {"depth": None}

    real_apply = bobreport._apply_merge_payload

    def wrap(doc, mid, payload):
        seen["depth"] = getattr(bobreport._LOCK_STATE, "depth", 0)
        return real_apply(doc, mid, payload)

    monkeypatch.setattr(bobreport, "_apply_merge_payload", wrap)
    out = bobreport.apply_callback(
        home, {"op": "merge", "machine": "marchhare", "weekly": 3}
    )
    assert out.ok is True
    assert seen["depth"] == 1
