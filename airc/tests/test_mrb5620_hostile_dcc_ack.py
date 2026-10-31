"""MRB #5620 hostile pins for FR #5612 reverse-DCC receiver ACK."""
from __future__ import annotations

import socket
import struct
import threading
import time
from pathlib import Path

import airc_dcc_bulk as dcc


def test_mrb5620_no_read_raises_exact_no_ack():
    ready = threading.Event()
    port_box: dict = {}

    def listen_sleep() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port_box["port"] = int(srv.getsockname()[1])
        srv.listen(1)
        srv.settimeout(5.0)
        ready.set()
        conn, _ = srv.accept()
        try:
            time.sleep(0.8)
        finally:
            conn.close()
            srv.close()

    t = threading.Thread(target=listen_sleep, daemon=True)
    t.start()
    assert ready.wait(2.0)
    try:
        dcc.reverse_dcc_send(
            b"hello-bulk",
            host="127.0.0.1",
            port=int(port_box["port"]),
            token=dcc.make_dcc_token(),
            timeout_s=0.4,
        )
        raise AssertionError("send must fail without receiver ack")
    except ConnectionError as exc:
        assert "dcc failed: no ack" in str(exc).lower()


def test_mrb5620_wrong_digest_ack_raises_no_ack():
    ready = threading.Event()
    port_box: dict = {}

    def listen_wrong() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port_box["port"] = int(srv.getsockname()[1])
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
        try:
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(64)
                if not chunk:
                    return
                buf += chunk
            rest = buf.split(b"\n", 1)[1]
            while len(rest) < 4:
                rest += conn.recv(4)
            (n,) = struct.unpack(">I", rest[:4])
            rest = rest[4:]
            while len(rest) < n:
                rest += conn.recv(n - len(rest))
            rest = rest[n:]
            while b"\n" not in rest:
                chunk = conn.recv(128)
                if not chunk:
                    return
                rest += chunk
            conn.sendall(b"ACK " + (b"0" * 64) + b"\n")
            time.sleep(0.2)
        finally:
            conn.close()
            srv.close()

    t = threading.Thread(target=listen_wrong, daemon=True)
    t.start()
    assert ready.wait(2.0)
    try:
        dcc.reverse_dcc_send(
            b"hello",
            host="127.0.0.1",
            port=int(port_box["port"]),
            token=dcc.make_dcc_token(),
            timeout_s=2.0,
        )
        raise AssertionError("wrong digest ACK must fail")
    except ConnectionError as exc:
        assert "dcc failed: no ack" in str(exc).lower()


def test_mrb5620_pins_expect_ack_and_docs():
    src = Path(dcc.__file__).read_text(encoding="utf-8")
    assert "_expect_ack" in src and "_send_ack" in src
    assert "FR #5612" in src
    assert "dcc failed: no ack" in src
    docs = Path(__file__).resolve().parents[1] / "docs" / "airc-remote-control.md"
    text = docs.read_text(encoding="utf-8")
    assert "ACK <sha256>" in text or "ACK <sha256>\\n" in text or "waits for `ACK" in text
    assert "FR #5612" in text
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-airc-commands"
        / "SKILL.md"
    )
    skill_text = skill.read_text(encoding="utf-8")
    assert "FR #5612" in skill_text
    assert "ACK <sha256>" in skill_text
    assert "DCC upload" in skill_text
    assert "via=dcc" in skill_text
