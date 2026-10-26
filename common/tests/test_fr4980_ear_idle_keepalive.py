"""FR #4980: bob-ear client PING keepalive detects half-open IRC links."""
from __future__ import annotations

import argparse
import socket
import time
from pathlib import Path
from unittest import mock

import pytest

import irc_agent


def _client(tmp_path: Path) -> irc_agent.Client:
    args = argparse.Namespace(
        host="127.0.0.1",
        port=6697,
        nick="Bob-testbox",
        realname="bob-ear",
        password="",
        channel="#testbox",
        home=str(tmp_path),
        chair=False,
        hello="",
        announce_key=False,
        once=False,
        debug=False,
        install_root="",
    )
    # Minimal construct without connecting.
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.args = args
    c.home = Path(tmp_path)
    c.original_nick = "Bob-testbox"
    c.live_nick = "Bob-testbox"
    c.channels = ["#testbox"]
    c.stop = __import__("threading").Event()
    c.dead = __import__("threading").Event()
    c.joined = __import__("threading").Event()
    c.joined.set()
    c.sock = mock.Mock()
    c.lock = __import__("threading").Lock()
    c.debug = None
    c._last_server_rx = time.time()
    c._pong_due_at = 0.0
    c._awaiting_client_pong = False
    c._last_client_ping = 0.0
    c._last_keepalive_log = 0.0
    c._no_reconnect = False
    return c


def test_idle_ping_and_dead_bounds():
    assert irc_agent.idle_ping_s() >= 15.0
    assert irc_agent.idle_dead_s() >= 30.0
    assert irc_agent.recv_timeout_s() <= irc_agent.idle_ping_s()


def test_idle_keepalive_sends_client_ping(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_IRC_IDLE_PING_S", "20")
    monkeypatch.setenv("BOB_IRC_IDLE_DEAD_S", "40")
    c = _client(tmp_path)
    c._last_server_rx = time.time() - 25.0
    sent = []

    def fake_send(line: str) -> None:
        sent.append(line)

    c.send = fake_send  # type: ignore[method-assign]
    c._idle_keepalive()
    assert len(sent) == 1
    assert sent[0].startswith("PING :be-")
    assert c._awaiting_client_pong is True


def test_idle_keepalive_reconnects_when_pong_overdue(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_IRC_IDLE_PING_S", "20")
    monkeypatch.setenv("BOB_IRC_IDLE_DEAD_S", "40")
    c = _client(tmp_path)
    c._awaiting_client_pong = True
    c._last_client_ping = time.time() - 50.0
    c._last_server_rx = time.time() - 50.0
    called = []

    def fake_reconnect() -> None:
        called.append("reconnect")
        c.dead.set()

    c.recv_idle_reconnect = fake_reconnect  # type: ignore[method-assign]
    c._idle_keepalive()
    assert called == ["reconnect"]
    assert c.dead.is_set()


def test_note_server_rx_clears_awaiting_pong(tmp_path):
    c = _client(tmp_path)
    c._awaiting_client_pong = True
    c._note_server_rx()
    assert c._awaiting_client_pong is False


def test_connect_sets_recv_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_IRC_RECV_TIMEOUT_S", "17")
    c = _client(tmp_path)
    raw = mock.Mock()
    sock = mock.Mock()
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: raw)
    ctx = mock.Mock()
    ctx.wrap_socket.return_value = sock
    monkeypatch.setattr(irc_agent.ssl, "create_default_context", lambda: ctx)
    out = c.connect()
    assert out is sock
    sock.settimeout.assert_called_with(pytest.approx(17.0))


def test_reader_timeout_runs_keepalive(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_IRC_IDLE_PING_S", "20")
    c = _client(tmp_path)
    c._last_server_rx = time.time() - 25.0
    calls = {"n": 0}

    def fake_recv(_n: int):
        calls["n"] += 1
        if calls["n"] == 1:
            raise socket.timeout()
        c.stop.set()
        return b""

    c.sock.recv = fake_recv
    sent = []
    c.send = lambda line: sent.append(line)  # type: ignore[method-assign]
    c.reader()
    assert any(s.startswith("PING :be-") for s in sent)


def test_docs_mention_fr4980_keepalive():
    root = Path(irc_agent.__file__).resolve().parents[2]
    doc = (root / "bob" / "docs" / "bob-ear.md").read_text(encoding="utf-8")
    assert "FR #4980" in doc or "#4980" in doc
    assert "keepalive" in doc.lower() or "idle-dead" in doc or "PING" in doc
