"""FR #5612: reverse DCC requires a receiver ACK before DONE via=dcc."""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import airc_dcc_bulk as dcc


def test_fr5612_roundtrip_still_delivers():
    payload = b"ack-me-" * 200
    got = dcc.reverse_dcc_roundtrip_localhost(payload, timeout_s=3.0)
    assert got == payload


def test_fr5612_no_read_means_no_ack(tmp_path=None):
    ready = threading.Event()
    port_box: dict = {}

    def listen_sleep():
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
    except (TimeoutError, ConnectionError, OSError, ValueError) as exc:
        msg = str(exc).lower()
        assert "ack" in msg or "timed" in msg or "timeout" in msg


def test_fr5612_pins():
    src = Path(dcc.__file__).read_text(encoding="utf-8")
    assert "FR #5612" in src
    assert "ACK " in src
    assert "_expect_ack" in src
    assert not Path(dcc.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
