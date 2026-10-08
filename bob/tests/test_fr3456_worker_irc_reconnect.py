"""FR #3456: bob-worker reconnects on IRC loss (VPN/network), keeps agent + ACKed job."""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import bob_worker as bw
from test_bob_worker_020 import FakeIrcd, Rig, make_seat, wait_until


class MultiAcceptIrcd:
    """Fake IRC that accepts many connections (reconnect)."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        self.received = []
        self.conns = []
        self.silent = False
        self._stop = threading.Event()
        self._lock = threading.Lock()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                self.srv.settimeout(0.3)
                c, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                self.conns.append(c)
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        buf = b""
        nick = "x"
        while not self._stop.is_set():
            try:
                c.settimeout(0.5)
                d = c.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not d:
                return
            buf += d
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                s = ln.decode().rstrip("\r")
                with self._lock:
                    self.received.append(s)
                if self.silent:
                    continue
                try:
                    if s.startswith("NICK "):
                        nick = s[5:]
                    if s.startswith("USER "):
                        c.sendall((":srv 001 %s :Welcome\r\n" % nick).encode())
                    if s.startswith("JOIN "):
                        c.sendall((":%s!u@h JOIN %s\r\n" % (nick, s[5:])).encode())
                    if s.startswith("PING "):
                        c.sendall((":srv PONG srv %s\r\n" % s[5:]).encode())
                except OSError:
                    return

    def drop_latest(self):
        with self._lock:
            c = self.conns[-1] if self.conns else None
        if c is None:
            return
        try:
            c.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            c.close()
        except OSError:
            pass

    def close(self):
        self._stop.set()
        try:
            self.srv.close()
        except OSError:
            pass
        with self._lock:
            for c in list(self.conns):
                try:
                    c.close()
                except OSError:
                    pass


def test_fr3456_drain_holds_unsent_lines_for_retry(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text(
        "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#3456 https://example/pull/1\n",
        encoding="utf-8",
    )
    payloads = []

    class FailSay:
        shop = "#marchhare"

        def say(self, target, text):
            return False

    n = bw.drain_outbox(path, FailSay(), lambda m: None, payloads.append)
    assert n == 0
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "DONE FR SimonBarnett/bobiverse#3456" in body
    assert payloads and "DONE FR" in payloads[0]


def test_fr3456_drain_flushes_held_line_when_alive(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text("PRIVMSG #marchhare :ACK FR o/r#1\n", encoding="utf-8")
    sent = []

    class OkSay:
        shop = "#marchhare"

        def say(self, target, text):
            sent.append(text)
            return True

    assert bw.drain_outbox(path, OkSay(), lambda m: None) == 1
    assert sent and "ACK FR o/r#1" in sent[0]
    assert path.read_text(encoding="utf-8") == ""


def test_fr3456_reconnect_keeps_agent_and_flushes_done(tmp_path):
    """Held DONE while down is flushed after reconnect; agent stays alive."""
    ircd = MultiAcceptIrcd()
    try:
        seat = bw.IrcSeat(
            "127.0.0.1",
            ircd.port,
            "marchhare-4242",
            "marchhare",
            tls=False,
            log=lambda m: None,
            send_gap_s=0.01,
        )
        rig = Rig(tmp_path, irc=seat, reconnect_grace_s=30.0, startup_grace_s=0)
        seat.log = rig.logs.append
        seat.on_message = rig.relay.deliver
        seat.connect(timeout=5)
        assert seat.alive
        assert rig.sup.bored is not None
        # Disable fuel watchers so mid-job polls cannot GIVEUP in unit tests.
        rig.sup.bored.fuel_lost_check_fn = None
        rig.sup.bored.fuel_check_fn = None
        rig.sup.bored.set_ready(True)
        rig.sup.bored.on_outbox("ACK FR SimonBarnett/bobiverse#3456")
        assert rig.sup.start_agent()
        agent = rig.procs[0].pid
        result = []
        threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
        ob = Path(rig.sup.run_dir) / "outbox.txt"
        bw.ensure_outbox(ob)
        # Fail-say path first: drain while "down" by dropping then writing DONE after loss
        ircd.drop_latest()
        assert wait_until(lambda: any("reconnect grace" in m for m in rig.logs), 3.0), rig.logs[-10:]
        time.sleep(0.2)
        assert agent not in rig.killed
        assert not rig.sup.done.is_set()
        ob.write_text(
            "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#3456 https://example/pull/9\n",
            encoding="utf-8",
        )
        assert wait_until(
            lambda: any("DONE FR SimonBarnett/bobiverse#3456" in s for s in ircd.received),
            10.0,
        ), ircd.received[-30:]
        assert agent not in rig.killed
        assert len(rig.spawned) == 1
        rig.sup.shutdown("test-done", 0)
        assert wait_until(lambda: bool(result), 2.0)
    finally:
        ircd.close()


def test_fr3456_reconnect_reacks_open_job(tmp_path):
    """After reconnect with open ACK (no DONE yet), seat re-sends ACK on the wire."""
    ircd = MultiAcceptIrcd()
    try:
        seat = bw.IrcSeat(
            "127.0.0.1",
            ircd.port,
            "marchhare-4243",
            "marchhare",
            tls=False,
            log=lambda m: None,
            send_gap_s=0.01,
        )
        rig = Rig(tmp_path, irc=seat, reconnect_grace_s=30.0, startup_grace_s=0)
        seat.log = rig.logs.append
        seat.on_message = rig.relay.deliver
        seat.connect(timeout=5)
        rig.sup.bored.fuel_lost_check_fn = None
        rig.sup.bored.fuel_check_fn = None
        rig.sup.bored.set_ready(True)
        rig.sup.bored.on_outbox("ACK FR SimonBarnett/bobiverse#3456")
        assert rig.sup.start_agent()
        agent = rig.procs[0].pid
        result = []
        threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
        ircd.drop_latest()
        assert wait_until(lambda: any("reconnect grace" in m for m in rig.logs), 3.0)
        assert wait_until(
            lambda: any(
                "re-ACK after reconnect" in m or "ACK FR SimonBarnett/bobiverse#3456" in s
                for m in rig.logs
                for s in [m]
            )
            or any("ACK FR SimonBarnett/bobiverse#3456" in s for s in ircd.received),
            10.0,
        ), (rig.logs[-20:], ircd.received[-20:])
        assert any("ACK FR SimonBarnett/bobiverse#3456" in s for s in ircd.received)
        assert agent not in rig.killed
        rig.sup.shutdown("test-done", 0)
        assert wait_until(lambda: bool(result), 2.0)
    finally:
        ircd.close()


def test_fr3456_grace_exhausted_exits_without_reconnect_loop(tmp_path):
    ircd = MultiAcceptIrcd()
    try:
        seat = bw.IrcSeat(
            "127.0.0.1",
            ircd.port,
            "marchhare-99",
            "marchhare",
            tls=False,
            log=lambda m: None,
            send_gap_s=0.01,
        )
        rig = Rig(tmp_path, irc=seat, reconnect_grace_s=0.8, startup_grace_s=0)
        seat.log = rig.logs.append
        seat.on_message = rig.relay.deliver
        seat.connect(timeout=5)
        assert rig.sup.start_agent()
        agent = rig.procs[0].pid
        result = []
        threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
        ircd.drop_latest()
        ircd.close()
        assert wait_until(lambda: rig.sup.done.is_set(), 6.0)
        assert wait_until(lambda: result == [bw.EXIT_IRC_LOST], 2.0)
        assert agent in rig.killed
        assert any("grace exhausted" in m or "irc-lost-grace" in m for m in rig.logs)
    finally:
        ircd.close()


def test_fr3456_grace_zero_keeps_legacy_immediate_exit(tmp_path):
    ircd = FakeIrcd()
    try:
        seat = make_seat(ircd)
        rig = Rig(tmp_path, irc=seat, reconnect_grace_s=0, startup_grace_s=0)
        seat.log = rig.logs.append
        seat.on_message = rig.relay.deliver
        seat.connect(timeout=5)
        rig.sup.start_agent()
        agent = rig.procs[0].pid
        result = []
        threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
        ircd.drop()
        assert wait_until(lambda: result == [bw.EXIT_IRC_LOST], 3.0)
        assert rig.killed == [agent]
    finally:
        ircd.close()
