"""FR #1136: BobCallback digest.lock watchdog — break stale/empty locks, /health, live lock kept."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import bobcallback
import bobreport
import registered_machines as rm


ALLOW = {"127.0.0.1", "::1"}


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    return tmp_path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 5.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_break_stale_empty_digest_lock(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "30")
    lock = bobreport.digest_lock_path(home)
    lock.write_bytes(b"")
    old = time.time() - 120
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is not None
    assert not lock.exists()


def test_break_stale_does_not_break_fresh_live_lock(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "30")
    lock = bobreport.digest_lock_path(home)
    ready = threading.Event()
    done = threading.Event()

    def holder():
        with bobreport.digest_lock(home, timeout_s=2.0):
            ready.set()
            done.wait(2.0)

    t = threading.Thread(target=holder)
    t.start()
    assert ready.wait(3)
    assert lock.exists()
    info = bobreport.break_stale_digest_lock(home)
    assert info is None, f"must not break live lock: {info}"
    assert lock.exists()
    done.set()
    t.join(timeout=5)


def test_health_reports_ok_and_lock_age(home):
    code, raw = bobcallback.handle_request("GET", "/health", {}, b"", "127.0.0.1", home, ALLOW)
    assert code == 200
    doc = json.loads(raw.decode("utf-8"))
    assert doc.get("ok") is True
    assert "lock_age_s" in doc
    assert "last_digest_write" in doc


def test_report_survives_empty_old_lock_via_server(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "5")
    lock = bobreport.digest_lock_path(home)
    lock.write_bytes(b"")
    old = time.time() - 120
    os.utime(lock, (old, old))

    port = _free_port()
    httpd = bobcallback.serve(home, host="127.0.0.1", port=port, allow_ips=ALLOW, filer=None)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        t0 = time.monotonic()
        status, raw = _http_json(
            "POST",
            f"http://127.0.0.1:{port}/bob/v1/report",
            {"op": "merge", "machine": "marchhare", "weekly": 7},
            timeout=8.0,
        )
        elapsed = time.monotonic() - t0
        assert status in (200, 204), raw[:200]
        assert elapsed < 5.0, f"hung {elapsed:.1f}s"
        h_status, h_raw = _http_json("GET", f"http://127.0.0.1:{port}/health", timeout=5.0)
        assert h_status == 200
        health = json.loads(h_raw.decode("utf-8"))
        assert health.get("ok") is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_digest_lock_busy_maps_to_503(home, monkeypatch):
    def boom(*a, **k):
        raise bobreport.DigestLockBusy("busy")

    monkeypatch.setattr(bobreport, "apply_callback", boom)
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"Content-Type": "application/json"},
        json.dumps({"op": "merge", "machine": "marchhare", "weekly": 1}).encode(),
        "127.0.0.1",
        home,
        ALLOW,
    )
    assert code == 503
