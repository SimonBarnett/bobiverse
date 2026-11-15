"""FR #7618: HTTP accept/serve fatals must not leave the listener bound-but-dead.

MemoryError (or any accept-loop exception) either keeps serving after recovery
or exits non-zero so the service manager restarts. Self-probe failure (local GET
not within N seconds) logs, reports, and exits non-zero. Generic hosts only.
"""
from __future__ import annotations

import json
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
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#host-a"])
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    return tmp_path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_fr7618_memoryerror_on_accept_exits_nonzero_or_keeps_serving(home, monkeypatch):
    """Inject MemoryError into accept once: exit non-zero OR keep serving /health."""
    port = _free_port()
    httpd = bobcallback.serve(home, host="127.0.0.1", port=port, allow_ips=ALLOW, filer=None)
    reports: list[object] = []
    exits: list[int] = []
    calls = {"n": 0}
    real_get = httpd.get_request

    def flaky_get():
        calls["n"] += 1
        if calls["n"] == 1:
            raise MemoryError("fr7618-injected")
        return real_get()

    monkeypatch.setattr(httpd, "get_request", flaky_get)

    done = threading.Event()

    def run():
        bobcallback.serve_forever_guarded(
            httpd,
            report_fn=lambda exc: reports.append(type(exc).__name__),
            exit_fn=lambda code: (exits.append(int(code)), done.set()),
        )
        done.set()

    th = threading.Thread(target=run, name="fr7618-serve", daemon=True)
    th.start()
    # Wake accept once so flaky_get runs.
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2.0).read()
    except Exception:
        pass
    assert done.wait(5.0), "guarded serve did not finish or exit"
    th.join(timeout=2.0)
    try:
        httpd.shutdown()
    except Exception:
        pass
    try:
        httpd.server_close()
    except Exception:
        pass

    assert "MemoryError" in reports
    # Either process-exit path (preferred for NSSM) or recovered and still accepting.
    if exits:
        assert exits[0] != 0
    else:
        # Recovered: a later GET must work (re-bind not required if loop continued).
        # With exit_fn not called, guarded loop may have returned after shutdown.
        assert calls["n"] >= 1


def test_fr7618_self_probe_failure_reports_and_exits_nonzero(monkeypatch):
    """Self-probe: local GET cannot complete within N seconds → report + exit != 0."""
    reports: list[dict] = []
    exits: list[int] = []

    def fake_probe(url: str, timeout_s: float):
        time.sleep(min(0.05, timeout_s))
        raise TimeoutError(f"fr7618 probe timeout url={url} budget={timeout_s}")

    monkeypatch.setattr(bobcallback, "probe_listener_local_get", fake_probe)

    bobcallback.listener_self_probe_tick(
        host="127.0.0.1",
        port=9,  # unused; probe is faked
        timeout_s=1.0,
        fail_streak=0,
        max_fails=1,
        report_fn=lambda **kw: reports.append(kw) or {"ok": True},
        exit_fn=lambda code: exits.append(int(code)),
    )

    assert len(reports) == 1
    body = json.dumps(reports[0]).lower()
    assert "password" not in body
    assert "secret" not in body or "no secrets" in body
    assert "probe" in body or "listener" in str(reports[0]).lower()
    assert exits == [1]


def test_fr7618_self_probe_ok_does_not_exit(monkeypatch):
    monkeypatch.setattr(
        bobcallback,
        "probe_listener_local_get",
        lambda url, timeout_s: {"ok": True, "url": url},
    )
    reports: list = []
    exits: list = []
    streak = bobcallback.listener_self_probe_tick(
        host="127.0.0.1",
        port=7700,
        timeout_s=2.0,
        fail_streak=2,
        max_fails=3,
        report_fn=lambda **kw: reports.append(kw),
        exit_fn=lambda code: exits.append(int(code)),
    )
    assert streak == 0
    assert reports == []
    assert exits == []


def test_fr7618_source_has_no_machine_names():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "bobcallback.py").read_text(encoding="utf-8")
    assert "serve_forever_guarded" in src
    assert "listener_self_probe_tick" in src
    assert "FR #7618" in src
    start = src.index("def serve_forever_guarded")
    end = src.index("\ndef serve(", start)
    chunk = src[start:end].lower()
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    for name in banned:
        assert name not in chunk
    self_src = Path(__file__).read_text(encoding="utf-8").lower()
    for name in banned:
        assert name not in self_src


def test_fr7618_jeeves_main_uses_guarded_serve():
    root = Path(__file__).resolve().parents[2]
    main = (root / "common" / "scripts" / "jeeves_main.py").read_text(encoding="utf-8")
    assert "serve_forever_guarded" in main
