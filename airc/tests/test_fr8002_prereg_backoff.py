"""FR #8002: never-registered reconnect must stay under Ergo's per-IP limit."""
from __future__ import annotations

import argparse
import errno
import socket
import sys
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import airc_console_service as svc  # noqa: E402

ERGO_IP_LIMIT_PER_10MIN = 32


def test_prereg_backoff_escalates_and_resets(monkeypatch):
    monkeypatch.delenv("AIRC_PREREG_FAILS", raising=False)
    monkeypatch.delenv("AIRC_PREREG_BACKOFF_MIN_S", raising=False)
    monkeypatch.delenv("AIRC_PREREG_BACKOFF_MAX_S", raising=False)
    assert svc.prereg_backoff_seconds(1) == svc.RECONNECT_MIN_S
    assert svc.prereg_backoff_seconds(4) <= svc.RECONNECT_MAX_S
    assert svc.prereg_backoff_seconds(4) < 600
    fifth = svc.prereg_backoff_seconds(5, rng=__import__("random").Random(1))
    assert fifth >= 600
    later = svc.prereg_backoff_seconds(8, rng=__import__("random").Random(1))
    assert later >= 1800
    assert svc.prereg_escalation_tier(4) == 0
    assert svc.prereg_escalation_tier(5) == 1
    assert svc.prereg_escalation_tier(6) == 2
    # A registration resets the streak to the short minimum.
    assert svc.prereg_backoff_seconds(1) == svc.RECONNECT_MIN_S


def test_prereg_window_stays_under_ergo_ip_limit():
    opened = svc.connections_in_prereg_window(600, rng=__import__("random").Random(0))
    assert opened < ERGO_IP_LIMIT_PER_10MIN
    # Two ports must not be counted twice inside one round.
    assert opened * len(svc.resolve_irc_ports(993)) < ERGO_IP_LIMIT_PER_10MIN


def test_connect_reset_does_not_open_the_next_port(monkeypatch):
    calls: list[int] = []

    def fake_create(addr, timeout=30):
        _host, port = addr
        calls.append(int(port))
        err = OSError(errno.ECONNRESET, "forcibly closed")
        err.winerror = 10054
        raise err

    monkeypatch.setattr(svc.socket, "create_connection", fake_create)
    args = argparse.Namespace(
        host="irc.example.test",
        port=993,
        tls=False,
        tls_insecure=False,
    )
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = args
    console.sock = None
    try:
        console.connect()
    except OSError:
        pass
    else:
        raise AssertionError("reset must raise")
    assert calls == [993]


def test_stop_during_long_backoff_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "example-not-a-secret")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "unit-box", "--home", str(tmp_path), "--shop-mode", "wonderland", "--no-tls"]
    )
    console = svc.AircConsoleService(args)
    logs: list[str] = []
    monkeypatch.setattr(svc, "info", lambda m: logs.append(m))

    def boom():
        raise ConnectionError("reset before registration")

    monkeypatch.setattr(console, "connect", boom)

    def sleep_and_stop(_seconds):
        if any(svc.PREREG_DROP_LOG in line for line in logs):
            console._stop.set()

    monkeypatch.setattr(svc.time, "sleep", sleep_and_stop)
    assert console.run() == 0
    assert any(svc.PREREG_DROP_LOG in line for line in logs)
