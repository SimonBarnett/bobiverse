"""FR #5003: bulk shell output over a direct TCP stream (DCC-style) instead of IRC lines.

IRC stays the control plane (command, auth, ACK, DONE). When output exceeds the
threshold, the console may push bytes on a reverse TCP connect (console dials
out --- NAT-friendly for customer boxes). Callers advertise listen endpoints
with ``DCCLISTEN id=<job> host=<ip> port=<n> token=<hex>``. If no peer is ready
within the handshake timeout, fall back to the existing IRC ``out``/``CONT`` path.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import socket
import struct
import threading
import time
from dataclasses import dataclass

DCC_BULK_LINE_THRESHOLD = int(os.environ.get("AIRC_DCC_BULK_LINE_THRESHOLD", "48"))
DCC_BULK_BYTE_THRESHOLD = int(os.environ.get("AIRC_DCC_BULK_BYTE_THRESHOLD", "12000"))
DCC_BULK_SIZE_CAP = int(os.environ.get("AIRC_DCC_BULK_SIZE_CAP", str(2 * 1024 * 1024)))
DCC_HANDSHAKE_TIMEOUT_S = float(os.environ.get("AIRC_DCC_HANDSHAKE_TIMEOUT_S", "3.0"))

_DCCLISTEN_RE = re.compile(
    r"(?is)^DCCLISTEN\s+id=([0-9a-f]{8})\s+host=(\S+)\s+port=(\d+)\s+token=([0-9a-f]{16,64})\s*$"
)
_DONE_TRAILING_RE = re.compile(
    r"(?i)^DONE\s+id=([0-9a-f]+)\s+exit=(-?\d+)(?:\s+(\S.*))?$"
)


@dataclass(frozen=True)
class DccListenOffer:
    job_id: str
    host: str
    port: int
    token: str


@dataclass(frozen=True)
class BulkPayload:
    job_id: str
    exit_code: int
    data: bytes
    sha256: str

    @property
    def nbytes(self) -> int:
        return len(self.data)


def should_use_dcc_bulk(*, piece_count: int, byte_count: int) -> bool:
    """True when IRC paging would flood Ergo (FR #5003)."""
    if piece_count >= DCC_BULK_LINE_THRESHOLD:
        return True
    if byte_count >= DCC_BULK_BYTE_THRESHOLD:
        return True
    return False


def build_bulk_bytes(stdout: str, stderr: str) -> bytes:
    """Canonical bulk body: stdout, then stderr with a marker, UTF-8."""
    parts: list[str] = []
    if stdout:
        parts.append(stdout if stdout.endswith("\n") else stdout + "\n")
    if stderr:
        parts.append("--- stderr ---\n")
        parts.append(stderr if stderr.endswith("\n") else stderr + "\n")
    raw = "".join(parts).encode("utf-8")
    if len(raw) > DCC_BULK_SIZE_CAP:
        raw = raw[:DCC_BULK_SIZE_CAP]
    return raw


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_dcc_token() -> str:
    return secrets.token_hex(16)


def parse_dcclisten(text: str) -> DccListenOffer | None:
    m = _DCCLISTEN_RE.match((text or "").strip())
    if not m:
        return None
    return DccListenOffer(
        job_id=m.group(1).lower(),
        host=m.group(2),
        port=int(m.group(3)),
        token=m.group(4).lower(),
    )


def format_done_via_dcc(
    job_id: str,
    exit_code: int,
    *,
    nbytes: int,
    sha256: str,
    via: str = "dcc",
) -> str:
    return (
        f"DONE id={job_id} exit={exit_code} "
        f"bytes={int(nbytes)} sha256={sha256} via={via}"
    )


def format_bulk_control_lines(payload: BulkPayload) -> list[str]:
    """IRC control-plane lines when bytes go over DCC (no body flood)."""
    hint = (
        f"out id={payload.job_id} seq=1 bulk bytes={payload.nbytes} "
        f"sha256={payload.sha256} (FR #5003 DCC)"
    )
    done = format_done_via_dcc(
        payload.job_id,
        payload.exit_code,
        nbytes=payload.nbytes,
        sha256=payload.sha256,
        via="dcc",
    )
    return [hint, done]


def parse_done_line(text: str) -> dict | None:
    """Parse DONE with optional trailing key=val fields (FR #5003)."""
    m = _DONE_TRAILING_RE.match((text or "").strip())
    if not m:
        return None
    out: dict = {"id": m.group(1).lower(), "exit": int(m.group(2))}
    rest = (m.group(3) or "").strip()
    for tok in rest.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.lower()] = v
    return out


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed early")
        buf.extend(chunk)
    return bytes(buf)


def reverse_dcc_send(
    payload: bytes,
    *,
    host: str,
    port: int,
    token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> None:
    """Console connects out and writes token + u32be len + body + sha256."""
    if len(payload) > DCC_BULK_SIZE_CAP:
        raise ValueError("payload over DCC_BULK_SIZE_CAP")
    digest = sha256_hex(payload).encode("ascii")
    with socket.create_connection((host, int(port)), timeout=timeout_s) as sock:
        sock.settimeout(timeout_s)
        header = token.encode("ascii") + b"\n" + struct.pack(">I", len(payload))
        sock.sendall(header)
        sock.sendall(payload)
        sock.sendall(digest + b"\n")


def listen_and_receive(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    expect_token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> tuple[bytes, str, int]:
    """Caller-side: bind, accept one reverse connect, return (data, sha256, port)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(1)
    srv.settimeout(timeout_s)
    bound_port = int(srv.getsockname()[1])
    try:
        conn, _addr = srv.accept()
    finally:
        srv.close()
    with conn:
        conn.settimeout(timeout_s)
        buf = bytearray()
        while b"\n" not in buf:
            chunk = conn.recv(64)
            if not chunk:
                raise ConnectionError("no token")
            buf.extend(chunk)
            if len(buf) > 128:
                raise ConnectionError("token too long")
        line, rest = bytes(buf).split(b"\n", 1)
        if line.decode("ascii").lower() != expect_token.lower():
            raise PermissionError("token mismatch")
        need = 4 - len(rest)
        if need > 0:
            rest = rest + _recv_exact(conn, need)
        (length,) = struct.unpack(">I", rest[:4])
        body_pref = rest[4:]
        if length > DCC_BULK_SIZE_CAP:
            raise ValueError("remote length over cap")
        remain = length - len(body_pref)
        body = body_pref + (_recv_exact(conn, remain) if remain > 0 else b"")
        dig_buf = bytearray()
        while b"\n" not in dig_buf:
            chunk = conn.recv(128)
            if not chunk:
                raise ConnectionError("no digest")
            dig_buf.extend(chunk)
        dig = bytes(dig_buf).split(b"\n", 1)[0].decode("ascii").lower()
        if dig != sha256_hex(body):
            raise ValueError("sha256 mismatch")
        return body, dig, bound_port


def reverse_dcc_roundtrip_localhost(payload: bytes, *, timeout_s: float = 2.0) -> bytes:
    """Test helper: listen + send on localhost; return received body."""
    token = make_dcc_token()
    holder: dict = {}
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = int(srv.getsockname()[1])
    srv.close()

    def _listen_fixed() -> None:
        data, dig, _p = listen_and_receive(
            host="127.0.0.1", port=port, expect_token=token, timeout_s=timeout_s
        )
        holder["data"] = data
        holder["dig"] = dig

    t = threading.Thread(target=_listen_fixed, daemon=True)
    t.start()
    time.sleep(0.05)
    reverse_dcc_send(
        payload, host="127.0.0.1", port=port, token=token, timeout_s=timeout_s
    )
    t.join(timeout=timeout_s + 1.0)
    if "data" not in holder:
        raise TimeoutError("localhost roundtrip failed")
    return holder["data"]
