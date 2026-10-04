"""FR #1388: bind :7700 before drain; break foreign live digest.lock holders."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
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


def test_break_foreign_live_lock_after_foreign_age(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "60")
    monkeypatch.setenv("BOB_DIGEST_LOCK_FOREIGN_S", "2")
    lock = bobreport.digest_lock_path(home)
    foreign_pid = os.getpid() + 99999
    monkeypatch.setattr(bobreport, "_pid_alive", lambda pid: int(pid) == foreign_pid)
    lock.write_text(f"{foreign_pid}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 5
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is not None
    assert info.get("reason") == "foreign-stale"
    assert info.get("pid") == foreign_pid
    assert not lock.exists()


def test_break_does_not_foreign_break_fresh_self_lock(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "60")
    monkeypatch.setenv("BOB_DIGEST_LOCK_FOREIGN_S", "2")
    lock = bobreport.digest_lock_path(home)
    ready = threading.Event()
    done = threading.Event()

    def holder():
        with bobreport.digest_lock(home, timeout_s=2.0):
            ready.set()
            done.wait(3.0)

    t = threading.Thread(target=holder)
    t.start()
    assert ready.wait(3)
    time.sleep(2.5)  # older than foreign age, but holder is this process's lock via thread
    # Holder PID is this interpreter — foreign-stale must not apply to self.
    info = bobreport.break_stale_digest_lock(home)
    assert info is None, f"must not break self lock: {info}"
    assert lock.exists()
    done.set()
    t.join(timeout=5)


def test_health_includes_lock_pid(home):
    code, raw = bobcallback.handle_request("GET", "/health", {}, b"", "127.0.0.1", home, ALLOW)
    assert code == 200
    doc = json.loads(raw.decode("utf-8"))
    assert "lock_pid" in doc
    assert doc.get("pid") == os.getpid()
    assert "lock_foreign_s" in doc


def test_serve_listens_even_when_drain_blocks(home, monkeypatch):
    """drain_pending must not delay ThreadingHTTPServer bind (FR #1388)."""
    gate = threading.Event()

    def stuck_drain(*_a, **_k):
        gate.wait(10)
        return []

    monkeypatch.setattr(bobcallback, "drain_pending", stuck_drain)
    port = _free_port()
    httpd = bobcallback.serve(home, host="127.0.0.1", port=port, allow_ips=ALLOW, filer=None)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        t0 = time.monotonic()
        # Must answer while drain is still blocked.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3.0) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.monotonic() - t0
        assert elapsed < 2.5, f"listen blocked by drain for {elapsed:.1f}s"
        assert body.get("ok") is True
    finally:
        gate.set()
        httpd.shutdown()


def test_webhooks_doc_mentions_foreign_and_bind_order():
    doc = Path(__file__).resolve().parents[1] / "docs" / "webhooks.md"
    text = doc.read_text(encoding="utf-8")
    assert "FR #1388" in text
    assert "foreign" in text.lower()
    assert "drain_pending" in text
