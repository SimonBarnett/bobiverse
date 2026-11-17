"""FR #7999: unit tests for the stdlib IRC-over-WebSocket transport adapter."""
from __future__ import annotations

import base64
import hashlib
import socket
import threading
import time
from pathlib import Path

import pytest

import airc_ws_transport as ws

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _accept(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + _GUID).encode("ascii")).digest()).decode("ascii")


def _server_frame(opcode: int, payload: bytes = b"", *, fin: bool = True, mask: bool = False) -> bytes:
    b0 = (0x80 if fin else 0x00) | opcode
    header = bytearray([b0])
    n = len(payload)
    if mask:
        header.append(0x80 | (n if n < 126 else 126))
    else:
        header.append(n if n < 126 else 126)
    if n >= 126:
        header += n.to_bytes(2, "big")
    body = payload
    if mask:
        m = b"\x01\x02\x03\x04"
        header += m
        body = bytes(b ^ m[i % 4] for i, b in enumerate(payload))
    return bytes(header) + body


def _recv_exact(conn, n: int, timeout: float = 3.0) -> bytes:
    conn.settimeout(timeout)
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError("peer closed")
        buf += chunk
    return buf


def _read_client_frame(conn) -> tuple[int, bytes, bool]:
    head = _recv_exact(conn, 2)
    b0, b1 = head[0], head[1]
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(conn, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(conn, 8), "big")
    mask = _recv_exact(conn, 4) if masked else b"\x00" * 4
    payload = _recv_exact(conn, length) if length else b""
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload, masked


class _WsPeer:
    """Minimal in-test WebSocket server (one connection)."""

    def __init__(self, *, subprotocol=None, status=101, accept=None, send_headers=b"") -> None:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = int(self._srv.getsockname()[1])
        self.subprotocol = subprotocol
        self.status = status
        self.accept_override = accept
        self.send_headers = send_headers
        self.conn: socket.socket | None = None
        self.request_head = b""
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        try:
            if self.conn is not None:
                self.conn.close()
        finally:
            self._srv.close()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/"

    def _serve(self) -> None:
        conn, _ = self._srv.accept()
        self.conn = conn
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk
        head, _rest = data.split(b"\r\n\r\n", 1)
        self.request_head = head
        key = ""
        for line in head.decode("latin-1").split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
        accept = self.accept_override or _accept(key)
        lines = [
            f"HTTP/1.1 {self.status} Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {accept}",
        ]
        if self.subprotocol:
            lines.append(f"Sec-WebSocket-Protocol: {self.subprotocol}")
        if self.send_headers:
            for extra in self.send_headers.decode("latin-1").splitlines():
                if extra.strip():
                    lines.append(extra.strip())
        resp = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        conn.sendall(resp)
        self.on_open(conn)

    def on_open(self, conn) -> None:  # noqa: ANN001
        pass


def test_safe_label_and_default_port():
    assert ws.safe_label("wss://wsirc.ntsa.uk") == "wss://wsirc.ntsa.uk:443/"
    assert ws.safe_label("ws://127.0.0.1:8080/") == "ws://127.0.0.1:8080/"
    assert ws.validate_url("wss://wsirc.ntsa.uk") == ("wss", "wsirc.ntsa.uk", 443, "/")
    # query string and userinfo never appear in the label
    assert ws.safe_label("wss://wsirc.ntsa.uk/x?token=secret") == "wss://wsirc.ntsa.uk:443/x"


def test_url_validation_rejects_userinfo_and_non_loopback_ws():
    with pytest.raises(ValueError):
        ws.validate_url("wss://user:pass@host/")
    with pytest.raises(ValueError):
        ws.validate_url("ws://example.com/")
    with pytest.raises(ValueError):
        ws.validate_url("http://host/")
    with pytest.raises(ValueError):
        ws.validate_url("")


def test_connect_ws_loopback_text_and_client_masks():
    with _WsPeer(subprotocol=None) as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            t.sendall(b"PING :1\r\n")
            opcode, payload, masked = _read_client_frame(peer.conn)
            assert opcode == 0x1  # text (no subprotocol selected -> text)
            assert masked
            assert payload == b"PING :1"
        finally:
            t.close()


def test_connect_ws_binary_subprotocol_uses_binary_frames():
    with _WsPeer(subprotocol="binary.ircv3.net") as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            t.sendall(b"PASS x\r\n")
            opcode, payload, _ = _read_client_frame(peer.conn)
            assert opcode == 0x2
            assert payload == b"PASS x"
        finally:
            t.close()


def test_connect_ws_text_subprotocol_uses_text_frames():
    with _WsPeer(subprotocol="text.ircv3.net") as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            t.sendall(b"NICK n\r\n")
            opcode, _, _ = _read_client_frame(peer.conn)
            assert opcode == 0x1
        finally:
            t.close()


def test_connect_ws_rejects_unexpected_subprotocol():
    with _WsPeer(subprotocol="custom.protocol") as peer:
        with pytest.raises(ws.WebSocketHandshakeError) as ei:
            ws.connect_ws(peer.url, timeout=3.0)
        assert "bad-subprotocol" in str(ei.value)


def test_connect_ws_rejects_bad_accept():
    with _WsPeer(accept="garbage") as peer:
        with pytest.raises(ws.WebSocketHandshakeError) as ei:
            ws.connect_ws(peer.url, timeout=3.0)
        assert "bad-accept" in str(ei.value)


def test_connect_ws_rejects_non_101():
    with _WsPeer(status=403, send_headers=b"Content-Length: 9") as peer:
        with pytest.raises(ws.WebSocketHandshakeError) as ei:
            ws.connect_ws(peer.url, timeout=3.0)
        reason = str(ei.value)
        assert "status=403" in reason
        # never leak headers or bodies
        assert "Content-Length" not in reason
        assert "Switching" not in reason


def test_sendall_one_message_per_line_no_crlf():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            t.sendall(b"A\r\nB\r\n")
            op1, p1, m1 = _read_client_frame(peer.conn)
            op2, p2, m2 = _read_client_frame(peer.conn)
            assert p1 == b"A" and m1
            assert p2 == b"B" and m2
        finally:
            t.close()


def test_recv_returns_crlf_terminated_and_buffers_remainder():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x1, b"hello"))
            assert t.recv(4096) == b"hello\r\n"
            # partial read buffering: recv(n) smaller than the message
            peer.conn.sendall(_server_frame(0x1, b"abcdef"))
            assert t.recv(3) == b"abc"
            assert t.recv(3) == b"def"
            assert t.recv(3) == b"\r\n"
        finally:
            t.close()


def test_recv_reassembles_fragmented_message():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x1, b"hello", fin=False))
            peer.conn.sendall(_server_frame(0x0, b" wor", fin=False))
            peer.conn.sendall(_server_frame(0x0, b"ld", fin=True))
            assert t.recv(4096) == b"hello world\r\n"
        finally:
            t.close()


def test_recv_replies_to_ping_between_fragments():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            result: dict[str, bytes] = {}

            def _run():
                result["msg"] = t.recv(4096)

            th = threading.Thread(target=_run, daemon=True)
            th.start()
            time.sleep(0.1)
            peer.conn.sendall(_server_frame(0x1, b"he", fin=False))
            peer.conn.sendall(_server_frame(0x9, b"probe"))
            opcode, payload, masked = _read_client_frame(peer.conn)
            assert opcode == 0xA and payload == b"probe" and masked
            peer.conn.sendall(_server_frame(0x0, b"y", fin=True))
            th.join(3.0)
            assert result.get("msg") == b"hey\r\n"
        finally:
            t.close()


def test_recv_close_returns_eof():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x8, b""))
            assert t.recv(4096) == b""
        finally:
            t.close()


def test_recv_oversize_message_rejected():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            # claim a data frame larger than the cap without sending the body
            header = bytearray([0x82])
            n = ws._MAX_MESSAGE_BYTES + 1
            header.append(127)
            header += n.to_bytes(8, "big")
            peer.conn.sendall(bytes(header))
            with pytest.raises(ws.WebSocketError):
                t.recv(4096)
        finally:
            t.close()


def test_recv_control_frame_too_long_rejected():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x9, b"\x00" * 126))
            with pytest.raises(ws.WebSocketError):
                t.recv(4096)
        finally:
            t.close()


def test_recv_fragmented_control_rejected():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x9, b"x", fin=False))
            with pytest.raises(ws.WebSocketError):
                t.recv(4096)
        finally:
            t.close()


def test_recv_masked_server_frame_rejected():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(3.0)
            peer.conn.sendall(_server_frame(0x1, b"x", mask=True))
            with pytest.raises(ws.WebSocketError):
                t.recv(4096)
        finally:
            t.close()


def test_recv_timeout_preserves_partial_frame():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(0.3)
            # send a partial 2-byte header for a 126-extended-length frame
            peer.conn.sendall(bytes([0x82, 126, 0x00]))
            with pytest.raises(socket.timeout):
                t.recv(4096)
            # complete the frame: ext-length byte + payload
            peer.conn.sendall(bytes([0x05]) + b"world")
            assert t.recv(4096) == b"world\r\n"
        finally:
            t.close()


def test_connect_ws_fails_cleanly_when_refused():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(ws.WebSocketHandshakeError):
        ws.connect_ws(f"ws://127.0.0.1:{port}/", timeout=1.0)


def test_transport_is_socket_compatible():
    with _WsPeer() as peer:
        t = ws.connect_ws(peer.url, timeout=3.0)
        try:
            t.settimeout(2.0)
            assert t.gettimeout() == 2.0
            assert isinstance(t.getsockname(), tuple)
            assert isinstance(t.getpeername(), tuple)
        finally:
            t.close()
            t.close()  # idempotent
