"""FR #8234: SASL success must still be able to send NICK/USER before 001."""
from __future__ import annotations

import socket
import threading
import time

import irc_agent


def _pair():
    if hasattr(socket, "socketpair"):
        try:
            a, b = socket.socketpair()
            a.settimeout(5)
            b.settimeout(5)
            return a, b
        except (AttributeError, OSError):
            pass
    gate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    gate.bind(("127.0.0.1", 0))
    gate.listen(1)
    port = gate.getsockname()[1]
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cli.settimeout(5)
    cli.connect(("127.0.0.1", port))
    srv, _addr = gate.accept()
    gate.close()
    srv.settimeout(5)
    return srv, cli


def _client(sock) -> irc_agent.Client:
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.lock = threading.Lock()
    c.ready = threading.Event()
    c.stop = threading.Event()
    c.dead = threading.Event()
    c.sock = sock
    c.debug = None
    return c


def test_fr8234_send_nick_while_reader_waits():
    srv, cli = _pair()
    try:
        c = _client(cli)
        held = threading.Event()

        def block_read():
            held.set()
            try:
                c._ssl_recv(64)
            except OSError:
                pass

        t = threading.Thread(target=block_read, daemon=True)
        t.start()
        assert held.wait(2)
        time.sleep(0.05)
        started = time.monotonic()
        c.send("NICK jeeves")
        assert time.monotonic() - started < 1.0
        srv.sendall(b":irc 001 jeeves :Welcome\r\n")
        t.join(2)
        assert not t.is_alive()
    finally:
        srv.close()
        cli.close()


def test_fr8234_sasl_then_nick_before_001(monkeypatch):
    """Ergo-like: after 903 the server sends nothing until NICK/USER/CAP END."""
    monkeypatch.setenv("BOB_IRC_SASL_USER", "jeeves")
    monkeypatch.setenv("BOB_IRC_SASL_PASSWORD", "EXAMPLE_SASL")
    srv, cli = _pair()
    try:
        c = _client(cli)
        c.sasl_ack = threading.Event()
        c.sasl_plus = threading.Event()
        c.sasl_903 = threading.Event()
        c.sasl_fail = threading.Event()
        c.live_nick = "jeeves"
        c.original_nick = "jeeves"
        c.args = type("A", (), {"realname": "jeeves"})()
        seen = []
        done = threading.Event()

        def server():
            buf = b""
            deadline = time.monotonic() + 8

            def pull(need):
                nonlocal buf
                while need(buf.decode("utf-8", "replace")) is False:
                    if time.monotonic() > deadline:
                        return False
                    try:
                        chunk = srv.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        return False
                    buf += chunk
                return True

            if not pull(lambda s: "CAP LS" in s or "CAP REQ" in s):
                return
            srv.sendall(b":irc CAP * ACK :sasl\r\n")
            if not pull(lambda s: "AUTHENTICATE PLAIN" in s):
                return
            srv.sendall(b"AUTHENTICATE +\r\n")
            if not pull(lambda s: s.count("AUTHENTICATE ") >= 2):
                return
            srv.sendall(b":irc 903 jeeves :SASL authentication successful\r\n")
            # No further server bytes until the client finishes registration.
            if not pull(lambda s: "NICK jeeves" in s and "USER jeeves" in s and "CAP END" in s):
                return
            seen.append("registered")
            srv.sendall(b":irc 001 jeeves :Welcome\r\n")
            if not pull(lambda s: "JOIN #bobiverse" in s):
                return
            srv.sendall(b":jeeves!u@h JOIN #bobiverse\r\n")
            seen.append("joined")
            done.set()

        def pump():
            buf = b""
            while not c.stop.is_set():
                try:
                    data = c._ssl_recv(4096)
                except (OSError, socket.timeout):
                    if c.stop.is_set() or done.is_set():
                        return
                    continue
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    wire = raw.decode("utf-8", "replace").rstrip("\r")
                    if wire.startswith("PING "):
                        c.send("PONG " + wire[5:])
                        continue
                    rest = wire[1:].partition(" ")[2] if wire.startswith(":") else wire
                    parts = rest.split(" ")
                    cmd = parts[0] if parts else ""
                    trailing = wire.split(" :", 1)[1] if " :" in wire else ""
                    for line in c.sasl_on_line(cmd, parts[1:], trailing) or []:
                        c.send(line)
                    if cmd == "001":
                        c.ready.set()

        threading.Thread(target=server, daemon=True).start()
        threading.Thread(target=pump, daemon=True).start()
        c.send("CAP LS 302")
        assert c.sasl_plain() is True
        c.send("NICK " + c.live_nick)
        c.send("USER %s 0 * :%s" % (c.live_nick, c.args.realname))
        assert c.ready.wait(2)
        c.send("JOIN #bobiverse")
        assert done.wait(5), "registration did not complete (NICK/USER/CAP END/JOIN after SASL)"
        assert seen == ["registered", "joined"]
    finally:
        c.dead.set()
        c.stop.set()
        srv.close()
        cli.close()
