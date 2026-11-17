#!/usr/bin/env python3
"""FR #7999: stdlib-only IRC-over-WebSocket (RFC 6455) transport for airc.

The console service treats ``self.sock`` as a CRLF-framed byte stream.  This
module provides a socket-compatible adapter so the existing IRC layer
(``send`` -> ``sendall``, ``read_loop`` -> ``recv``) works unchanged over a
Cloudflare-proxied ``wss://`` endpoint on 443 when raw TLS IRC on 993/6697 is
reset by a customer egress firewall.

Contract (must be preserved, not changed):
- ``sendall(data)`` splits on LF, strips CR, and sends each non-empty IRC line
  as one masked WebSocket message with no line terminator.
- ``recv(n)`` returns message bytes terminated with ``b"\\r\\n"`` (buffering any
  remainder above ``n``), ``b""`` on clean close, and re-raises ``socket.timeout``
  so the one-second wake-up in ``read_loop`` is untouched.
- Every failure is an ``OSError`` subclass.  Exception text carries only an
  allowlisted reason --- never headers, response bodies, or query strings.

Only stdlib is imported so PyInstaller picks it up by static analysis.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import threading
from urllib.parse import urlsplit

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
# Ergo's native ``websocket`` listener negotiates the IRCv3 subprotocols below.
_OFFERED_SUBPROTOCOLS = ("text.ircv3.net", "binary.ircv3.net")
_MAX_MESSAGE_BYTES = 1 << 20  # 1 MiB
_MAX_HANDSHAKE_BYTES = 1 << 16
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

_OP_CONT = 0x0
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA


class WebSocketError(OSError):
    """Base for all transport failures (socket-compatible OSError subclass)."""


class WebSocketHandshakeError(WebSocketError):
    """Handshake/connect failure carrying only an allowlisted reason string."""


def validate_url(url: str) -> tuple[str, str, int, str]:
    """Parse and validate a ``ws://``/``wss://`` URL.

    Returns ``(scheme, host, port, path)``.  Rejects userinfo and non-loopback
    ``ws://``.  Defaults the port to 443 (wss) / 80 (ws).  Never raises with a
    message that includes credentials or a query string.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("empty websocket url")
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "").lower()
    if scheme not in ("ws", "wss"):
        raise ValueError("websocket url scheme must be ws or wss")
    if parts.username is not None or parts.password is not None:
        raise ValueError("websocket url userinfo is not allowed")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise ValueError("websocket url missing host")
    port = parts.port
    if port is None:
        port = 443 if scheme == "wss" else 80
    if scheme == "ws" and host not in _LOOPBACK_HOSTS:
        raise ValueError("ws:// is only allowed on loopback")
    path = parts.path or "/"
    return scheme, host, int(port), path


def safe_label(url: str) -> str:
    """Scheme/host/port/path only --- no userinfo, no query string, no fragment."""
    scheme, host, port, path = validate_url(url)
    host_label = f"[{host}]" if ":" in host else host
    return f"{scheme}://{host_label}:{port}{path}"


def _read_http_response(sock) -> tuple[int, dict[str, str], bytes]:
    """Read the upgrade response head.  Returns (status, headers, leftover)."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        try:
            chunk = sock.recv(4096)
        except (socket.timeout, TimeoutError):
            raise WebSocketHandshakeError("timeout")
        if not chunk:
            raise WebSocketHandshakeError("truncated-response")
        data += chunk
        if len(data) > _MAX_HANDSHAKE_BYTES:
            raise WebSocketHandshakeError("oversize-response")
    head, _, rest = bytes(data).partition(b"\r\n\r\n")
    lines = head.decode("latin-1", errors="replace").split("\r\n")
    if not lines:
        raise WebSocketHandshakeError("bad-status-line")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2:
        raise WebSocketHandshakeError("bad-status-line")
    try:
        status = int(parts[1])
    except ValueError:
        raise WebSocketHandshakeError("bad-status-line")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return status, headers, rest


class WebSocketTransport:
    """Socket-compatible adapter over an established WebSocket connection."""

    def __init__(
        self,
        sock,
        *,
        scheme: str,
        host: str,
        port: int,
        path: str,
        subprotocol: str | None,
        leftover: bytes = b"",
    ) -> None:
        self._sock = sock
        self._scheme = scheme
        self._host = host
        self._port = port
        self._path = path
        self._subprotocol = subprotocol
        self._opcode = _OP_BINARY if subprotocol == "binary.ircv3.net" else _OP_TEXT
        self._rbuf = bytearray(leftover)
        self._read_buf = b""
        self._frag_opcode: int | None = None
        self._frag_buf = bytearray()
        self._write_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = False

    # --- socket-compatible surface -------------------------------------

    def settimeout(self, value) -> None:
        self._sock.settimeout(value)

    def gettimeout(self):
        return self._sock.gettimeout()

    def getsockname(self):
        return self._sock.getsockname()

    def getpeername(self):
        return self._sock.getpeername()

    def fileno(self):
        return self._sock.fileno()

    def sendall(self, data: bytes) -> None:
        if self._closed:
            raise OSError("socket closed")
        with self._write_lock:
            for line in data.split(b"\n"):
                line = line.rstrip(b"\r")
                if not line:
                    continue
                self._send_frame(self._opcode, line)

    def recv(self, n: int) -> bytes:
        if self._closed:
            return b""
        if self._read_buf:
            out = self._read_buf[:n]
            self._read_buf = self._read_buf[n:]
            return out
        while True:
            msg = self._next_message()
            if msg is None:
                return b""
            data = bytes(msg) + b"\r\n"
            if not data:
                continue
            out = data[:n]
            self._read_buf = data[n:]
            return out

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        try:
            with self._write_lock:
                self._send_frame(_OP_CLOSE, b"")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    # --- frame layer ----------------------------------------------------

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += n.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += n.to_bytes(8, "big")
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _next_message(self) -> bytes | None:
        """Return the next complete message, or ``None`` on a clean close."""
        while True:
            frame = self._read_frame()
            if frame is None:
                return None
            fin, opcode, payload = frame
            if opcode == _OP_CLOSE:
                self._reply_close()
                return None
            if opcode == _OP_PING:
                with self._write_lock:
                    self._send_frame(_OP_PONG, payload)
                continue
            if opcode == _OP_PONG:
                continue
            if opcode in (_OP_TEXT, _OP_BINARY):
                if self._frag_opcode is not None:
                    raise WebSocketError("data-during-fragment")
                if fin:
                    return bytes(payload)
                self._frag_opcode = opcode
                self._frag_buf = bytearray(payload)
                continue
            if opcode == _OP_CONT:
                if self._frag_opcode is None:
                    raise WebSocketError("stray-continuation")
                self._frag_buf += payload
                if len(self._frag_buf) > _MAX_MESSAGE_BYTES:
                    raise WebSocketError("oversize-message")
                if fin:
                    msg = bytes(self._frag_buf)
                    self._frag_opcode = None
                    self._frag_buf = bytearray()
                    return msg
                continue
            raise WebSocketError("bad-opcode")

    def _fill(self, n: int) -> bool:
        """Ensure ``_rbuf`` holds ``n`` bytes.  False on clean EOF; timeout re-raised."""
        while len(self._rbuf) < n:
            try:
                chunk = self._sock.recv(65536)
            except (socket.timeout, TimeoutError):
                raise
            if not chunk:
                return False
            self._rbuf += chunk
        return True

    def _read_frame(self) -> tuple[bool, int, bytes] | None:
        # Read the whole variable-length header before consuming any byte, so a
        # mid-header timeout leaves the partial header intact for a clean resume.
        if not self._fill(2):
            return None
        b0, b1 = self._rbuf[0], self._rbuf[1]
        if b0 & 0x70:
            raise WebSocketError("reserved-bits")
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        header_len = 2
        if length == 126:
            header_len = 4
        elif length == 127:
            header_len = 10
        if not self._fill(header_len):
            return None
        if length == 126:
            length = int.from_bytes(bytes(self._rbuf[2:4]), "big")
        elif length == 127:
            length = int.from_bytes(bytes(self._rbuf[2:10]), "big")
        if masked:
            raise WebSocketError("masked-server-frame")
        if opcode >= _OP_CLOSE:
            if length > 125:
                raise WebSocketError("control-too-long")
            if not fin:
                raise WebSocketError("fragmented-control")
        elif length > _MAX_MESSAGE_BYTES:
            raise WebSocketError("oversize-message")
        del self._rbuf[:header_len]
        payload = b""
        if length:
            if not self._fill(length):
                return None
            payload = bytes(self._rbuf[:length])
            del self._rbuf[:length]
        return fin, opcode, payload

    def _reply_close(self) -> None:
        try:
            with self._write_lock:
                self._send_frame(_OP_CLOSE, b"")
        except OSError:
            pass


def connect_ws(
    url: str,
    timeout: float = 30.0,
    verify: bool = True,
) -> WebSocketTransport:
    """Open a WebSocket and return a socket-compatible transport.

    ``verify`` mirrors ``--tls-insecure`` (disable TLS cert verification).
    """
    scheme, host, port, path = validate_url(url)
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise WebSocketHandshakeError(f"connect-failed {type(exc).__name__}") from exc
    raw.settimeout(timeout)
    sock = raw
    try:
        if scheme == "wss":
            ctx = ssl.create_default_context()
            if not verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            try:
                sock = ctx.wrap_socket(raw, server_hostname=host)
            except OSError as exc:
                raise WebSocketHandshakeError(f"tls-failed {type(exc).__name__}") from exc
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        host_header = host if ":" not in host else f"[{host}]"
        host_header += "" if port in (443, 80) else f":{port}"
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: " + ", ".join(_OFFERED_SUBPROTOCOLS) + "\r\n"
            "\r\n"
        )
        try:
            sock.sendall(req.encode("ascii"))
        except OSError as exc:
            raise WebSocketHandshakeError(f"send-failed {type(exc).__name__}") from exc
        status, headers, leftover = _read_http_response(sock)
        if status != 101:
            raise WebSocketHandshakeError(f"status={status}")
        expected = base64.b64encode(
            hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        accept = headers.get("sec-websocket-accept", "").strip()
        if accept != expected:
            raise WebSocketHandshakeError("bad-accept")
        protocol = headers.get("sec-websocket-protocol", "").strip()
        if protocol and protocol not in _OFFERED_SUBPROTOCOLS:
            raise WebSocketHandshakeError("bad-subprotocol")
        return WebSocketTransport(
            sock,
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            subprotocol=protocol or None,
            leftover=leftover,
        )
    except WebSocketHandshakeError:
        _safe_close(sock)
        raise
    except OSError as exc:
        _safe_close(sock)
        raise WebSocketHandshakeError(f"handshake-failed {type(exc).__name__}") from exc


def _safe_close(sock) -> None:
    try:
        sock.close()
    except OSError:
        pass
