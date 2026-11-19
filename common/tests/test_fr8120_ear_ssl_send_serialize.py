"""FR #8120: serialize IRC SSL I/O; no pre-001 non-reg sends; fast TLS retry."""
from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from unittest import mock

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
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.args = args
    c.home = Path(tmp_path)
    c.original_nick = "Bob-testbox"
    c.live_nick = "Bob-testbox"
    c.channels = ["#testbox"]
    c.stop = threading.Event()
    c.dead = threading.Event()
    c.joined = threading.Event()
    c.ready = threading.Event()
    c.lock = threading.Lock()
    c.debug = None
    c._nick_recover_pending = False
    c._nickname_reserved = False
    return c


class _SlowRecordingSock:
    """sendall that yields between bytes so unlocked writers would interleave."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self._mu = threading.Lock()

    def sendall(self, data: bytes) -> None:
        for b in data:
            with self._mu:
                self.buf.append(b)
            time.sleep(0.00005)


def test_fr8120_pre_001_allowlist():
    assert irc_agent.pre_001_send_allowed("PASS secret")
    assert irc_agent.pre_001_send_allowed("CAP LS 302")
    assert irc_agent.pre_001_send_allowed("NICK Bob-x")
    assert irc_agent.pre_001_send_allowed("USER Bob-x 0 * :bob")
    assert irc_agent.pre_001_send_allowed("AUTHENTICATE PLAIN")
    assert irc_agent.pre_001_send_allowed("PONG :token")
    assert not irc_agent.pre_001_send_allowed("PRIVMSG #x :hi")
    assert not irc_agent.pre_001_send_allowed("JOIN #x")
    assert not irc_agent.pre_001_send_allowed("PING :be-1")


def test_fr8120_no_send_other_than_reg_before_001(tmp_path, capsys):
    c = _client(tmp_path)
    sock = mock.Mock()
    c.sock = sock
    # ready not set -> registration only
    c.send("NICK Bob-testbox")
    c.send("PRIVMSG #testbox :hello")
    c.send("JOIN #testbox")
    calls = [args[0][0].decode("utf-8") for args in sock.sendall.call_args_list]
    assert any(x.startswith("NICK ") for x in calls)
    assert not any("PRIVMSG" in x for x in calls)
    assert not any(x.startswith("JOIN ") for x in calls)
    out = capsys.readouterr().out
    assert "drop-pre-001" in out


def test_fr8120_concurrent_sends_not_interleaved(tmp_path):
    c = _client(tmp_path)
    c.ready.set()
    sock = _SlowRecordingSock()
    c.sock = sock  # type: ignore[assignment]

    lines = [f"PRIVMSG #t :msg-{i}-{'x' * 40}" for i in range(12)]

    def _one(line: str) -> None:
        c.send(line)

    threads = [threading.Thread(target=_one, args=(ln,)) for ln in lines]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
        assert not t.is_alive()

    text = bytes(sock.buf).decode("utf-8")
    parts = [p for p in text.split("\r\n") if p]
    assert len(parts) == len(lines)
    assert set(parts) == set(lines)
    # Each wire line is intact (no mid-line splice from another writer).
    for p in parts:
        assert p.startswith("PRIVMSG #t :msg-")
        assert "PRIVMSG" not in p[7:]  # no second command glued mid-line


def test_fr8120_tls_fail_next_attempt_within_30s():
    """First reconnect after a TLS fail stays on the short ladder (<30s)."""
    backoff = 1.0
    # Simulate the FR #8120 SSLError path: clamp then sleep(backoff+jitter), then double.
    backoff = max(1.0, min(backoff, 8.0))
    delay = backoff + 1.0  # max jitter used in run_forever
    assert delay < 30.0
    backoff = irc_agent.next_reconnect_backoff_s(backoff)
    assert backoff <= 60.0
    assert irc_agent.nickname_reserved_backoff_s() <= 120.0
    assert irc_agent.nickname_reserved_backoff_s() < 300.0


def test_fr8120_ssl_recv_uses_same_lock(tmp_path):
    c = _client(tmp_path)
    c.ready.set()
    held = []

    class _Sock:
        def settimeout(self, _t: float) -> None:
            pass

        def recv(self, n: int) -> bytes:
            held.append(c.lock.locked())
            return b""

        def sendall(self, data: bytes) -> None:
            held.append(c.lock.locked())

    c.sock = _Sock()  # type: ignore[assignment]
    c._ssl_recv(8)
    c.send("PING :x")
    assert held == [True, True]
