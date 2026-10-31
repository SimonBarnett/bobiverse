"""FR #5003 / #5008: bulk shell output over a reverse TCP/TLS stream (DCC-style).

IRC stays the control plane (command, auth, ACK, DONE). When output exceeds the
threshold, the console may push bytes on a reverse connect (console dials out).
Callers advertise listen endpoints with::

  DCCLISTEN id=<job> host=<ip> port=<n> token=<hex> [tls=0|1] [relay=<host:port>]

FR #5008: TLS wrap (default on), optional ionos/local relay when neither side is
reachable, and a bob-ear / Invoke-AircRemote DCCLISTEN helper that verifies sha256.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass

DCC_BULK_LINE_THRESHOLD = int(os.environ.get("AIRC_DCC_BULK_LINE_THRESHOLD", "48"))
DCC_BULK_BYTE_THRESHOLD = int(os.environ.get("AIRC_DCC_BULK_BYTE_THRESHOLD", "12000"))
DCC_BULK_SIZE_CAP = int(os.environ.get("AIRC_DCC_BULK_SIZE_CAP", str(2 * 1024 * 1024)))
DCC_HANDSHAKE_TIMEOUT_S = float(os.environ.get("AIRC_DCC_HANDSHAKE_TIMEOUT_S", "3.0"))

# FR #5008 / MRB #5013: never embed RSA private key PEM in source (GitGuardian).
# Ephemeral self-signed SAN localhost is generated at runtime (cryptography),
# or load AIRC_DCC_TLS_CERT / AIRC_DCC_TLS_KEY paths.
_EPHEMERAL_TLS_PEM: tuple[str, str] | None = None


def _generate_ephemeral_tls_pem() -> tuple[str, str]:
    """Return (cert_pem, key_pem) for SAN DNS:localhost + IP:127.0.0.1."""
    try:
        from datetime import datetime, timedelta, timezone

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover - frozen/dev without crypto
        raise RuntimeError(
            "DCC TLS needs the cryptography package or AIRC_DCC_TLS_CERT/KEY env paths"
        ) from exc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "airc-dcc-bulk")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return cert_pem, key_pem


def _default_tls_pem() -> tuple[str, str]:
    global _EPHEMERAL_TLS_PEM
    if _EPHEMERAL_TLS_PEM is None:
        _EPHEMERAL_TLS_PEM = _generate_ephemeral_tls_pem()
    return _EPHEMERAL_TLS_PEM



_DCCLISTEN_RE = re.compile(
    r"(?is)^DCCLISTEN\s+id=([0-9a-f]{8})\s+host=(\S+)\s+port=(\d+)\s+token=([0-9a-f]{16,64})"
    r"(?:\s+tls=([01]))?(?:\s+relay=(\S+))?\s*$"
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
    tls: bool = True  # FR #5008: TLS wrap (token alone is not enough)
    relay: str | None = None  # host:port relay when both sides NAT'd


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
    tls_g = m.group(5)
    tls = True if tls_g is None else (tls_g == "1")
    relay = m.group(6)
    return DccListenOffer(
        job_id=m.group(1).lower(),
        host=m.group(2),
        port=int(m.group(3)),
        token=m.group(4).lower(),
        tls=tls,
        relay=(relay.strip() if relay else None),
    )


def format_dcclisten(offer: DccListenOffer) -> str:
    """Serialize a DCCLISTEN control line (FR #5008 helper)."""
    parts = [
        f"DCCLISTEN id={offer.job_id} host={offer.host} port={int(offer.port)} "
        f"token={offer.token} tls={1 if offer.tls else 0}"
    ]
    if offer.relay:
        parts[0] += f" relay={offer.relay}"
    return parts[0]


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


def _read_framed_bulk(sock: socket.socket, expect_token: str) -> tuple[bytes, str]:
    """Read token\\n + u32be len + body + sha256\\n and verify.

    A single recv may include length+body+digest; always slice body to `length`
    and keep leftovers for the digest line (small-payload Windows race).
    """
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(64)
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
        rest = rest + _recv_exact(sock, need)
    (length,) = struct.unpack(">I", rest[:4])
    if length > DCC_BULK_SIZE_CAP:
        raise ValueError("remote length over cap")
    rest = rest[4:]
    if len(rest) < length:
        rest = rest + _recv_exact(sock, length - len(rest))
    body = rest[:length]
    dig_buf = bytearray(rest[length:])
    while b"\n" not in dig_buf:
        chunk = sock.recv(128)
        if not chunk:
            raise ConnectionError("no digest")
        dig_buf.extend(chunk)
    dig = bytes(dig_buf).split(b"\n", 1)[0].decode("ascii").lower()
    if dig != sha256_hex(body):
        raise ValueError("sha256 mismatch")
    return body, dig


def _write_framed_bulk(sock: socket.socket, payload: bytes, token: str) -> None:
    digest = sha256_hex(payload).encode("ascii")
    header = token.encode("ascii") + b"\n" + struct.pack(">I", len(payload))
    sock.sendall(header)
    sock.sendall(payload)
    sock.sendall(digest + b"\n")


def _pin_tls12(ctx: ssl.SSLContext) -> ssl.SSLContext:
    """Pin TLS 1.2: TLS 1.3 + immediate client close races wrap_socket on Windows."""
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass
    return ctx


def load_tls_server_context(
    *,
    cert_pem: str | None = None,
    key_pem: str | None = None,
) -> ssl.SSLContext:
    """Server TLS. Prefers AIRC_DCC_TLS_CERT/KEY env paths, else ephemeral PEM."""
    import tempfile

    ctx = _pin_tls12(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER))
    cert_file = os.environ.get("AIRC_DCC_TLS_CERT")
    key_file = os.environ.get("AIRC_DCC_TLS_KEY")
    if cert_file and key_file:
        ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
        return ctx
    if cert_pem is None or key_pem is None:
        gen_cert, gen_key = _default_tls_pem()
        cert = cert_pem or gen_cert
        key = key_pem or gen_key
    else:
        cert = cert_pem
        key = key_pem
    c = tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem", encoding="ascii")
    k = tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem", encoding="ascii")
    try:
        c.write(cert)
        c.flush()
        c.close()
        k.write(key)
        k.flush()
        k.close()
        ctx.load_cert_chain(certfile=c.name, keyfile=k.name)
    finally:
        try:
            os.unlink(c.name)
        except OSError:
            pass
        try:
            os.unlink(k.name)
        except OSError:
            pass
    return ctx


def load_tls_client_context() -> ssl.SSLContext:
    """Client TLS. Default insecure for self-signed bulk; token still gates auth."""
    if os.environ.get("AIRC_DCC_TLS_INSECURE", "1") == "1":
        ctx = ssl._create_unverified_context()
    else:
        ctx = ssl.create_default_context()
    return _pin_tls12(ctx)


def reverse_dcc_send(
    payload: bytes,
    *,
    host: str,
    port: int,
    token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
    tls: bool = False,
) -> None:
    """Console connects out and writes token + u32be len + body + sha256.

    FR #5008: pass ``tls=True`` to wrap the stream (default False keeps WP1 tests).
    """
    if len(payload) > DCC_BULK_SIZE_CAP:
        raise ValueError("payload over DCC_BULK_SIZE_CAP")
    raw = socket.create_connection((host, int(port)), timeout=timeout_s)
    sock: socket.socket = raw
    try:
        if tls:
            sni = (
                "localhost"
                if host in {"127.0.0.1", "::1", "localhost"}
                else (host or "localhost")
            )
            sock = load_tls_client_context().wrap_socket(raw, server_hostname=sni)
        sock.settimeout(timeout_s)
        _write_framed_bulk(sock, payload, token)
        try:
            sock.shutdown(socket.SHUT_WR)
        except Exception:
            pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


def listen_and_receive(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    expect_token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
    tls: bool = False,
    ready: threading.Event | None = None,
) -> tuple[bytes, str, int]:
    """Caller-side: bind, accept one reverse connect, return (data, sha256, port)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(1)
    srv.settimeout(timeout_s)
    bound_port = int(srv.getsockname()[1])
    tls_ctx = load_tls_server_context() if tls else None
    if ready is not None:
        ready.set()
    try:
        conn, _addr = srv.accept()
    finally:
        srv.close()
    try:
        if tls_ctx is not None:
            conn = tls_ctx.wrap_socket(conn, server_side=True)
        conn.settimeout(timeout_s)
        body, dig = _read_framed_bulk(conn, expect_token)
        return body, dig, bound_port
    finally:
        try:
            conn.close()
        except Exception:
            pass


def reverse_dcc_roundtrip_localhost(payload: bytes, *, timeout_s: float = 2.0) -> bytes:
    """Test helper: listen + send on localhost; return received body."""
    token = make_dcc_token()
    holder: dict = {}
    port_box: dict = {}
    ready = threading.Event()
    err: list[BaseException] = []

    def _listen_fixed() -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            port_box["port"] = int(srv.getsockname()[1])
            srv.listen(1)
            srv.settimeout(timeout_s)
            ready.set()
            try:
                conn, _ = srv.accept()
            finally:
                srv.close()
            try:
                conn.settimeout(timeout_s)
                data, dig = _read_framed_bulk(conn, token)
                holder["data"] = data
                holder["dig"] = dig
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=_listen_fixed, daemon=True)
    t.start()
    if not ready.wait(timeout=timeout_s):
        raise TimeoutError("listen not ready")
    reverse_dcc_send(
        payload,
        host="127.0.0.1",
        port=int(port_box["port"]),
        token=token,
        timeout_s=timeout_s,
    )
    t.join(timeout=timeout_s + 1.0)
    if err:
        raise err[0]
    if "data" not in holder:
        raise TimeoutError("localhost roundtrip failed")
    return holder["data"]


def run_pair_relay(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    expect_token: str,
    timeout_s: float = 10.0,
    ready: threading.Event | None = None,
) -> int:
    """FR #5008 relay: two connects with ROLE caller|console <token>, then bridge.

    Leftover bytes after each ROLE line are forwarded so console may send bulk
    framing in the same TCP segment as ROLE.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(2)
    srv.settimeout(timeout_s)
    bound = int(srv.getsockname()[1])
    if ready is not None:
        ready.set()

    def _read_role(c: socket.socket) -> tuple[str, str, bytes]:
        buf = bytearray()
        while b"\n" not in buf:
            chunk = c.recv(128)
            if not chunk:
                raise ConnectionError("relay role closed")
            buf.extend(chunk)
            if len(buf) > 256:
                raise ConnectionError("relay role too long")
        line_b, leftover = bytes(buf).split(b"\n", 1)
        line = line_b.decode("ascii", errors="replace").strip()
        parts = line.split()
        if len(parts) != 3 or parts[0].upper() != "ROLE":
            raise ValueError("bad relay role line")
        return parts[1].lower(), parts[2].lower(), leftover

    c1, _ = srv.accept()
    c2, _ = srv.accept()
    srv.close()
    try:
        c1.settimeout(timeout_s)
        c2.settimeout(timeout_s)
        r1, t1, left1 = _read_role(c1)
        r2, t2, left2 = _read_role(c2)
        tok = expect_token.lower()
        if t1 != tok or t2 != tok:
            raise PermissionError("relay token mismatch")
        roles = {r1: c1, r2: c2}
        left = {r1: left1, r2: left2}
        if set(roles) != {"caller", "console"}:
            raise ValueError("relay needs caller+console")

        for role, peer_role in (("console", "caller"), ("caller", "console")):
            chunk = left.get(role) or b""
            if chunk:
                try:
                    roles[peer_role].sendall(chunk)
                except Exception:
                    pass

        def _pipe(a: socket.socket, b: socket.socket) -> None:
            try:
                while True:
                    chunk = a.recv(65536)
                    if not chunk:
                        break
                    b.sendall(chunk)
            except Exception:
                pass
            try:
                b.shutdown(socket.SHUT_WR)
            except Exception:
                pass

        t_ab = threading.Thread(
            target=_pipe, args=(roles["console"], roles["caller"]), daemon=True
        )
        t_ba = threading.Thread(
            target=_pipe, args=(roles["caller"], roles["console"]), daemon=True
        )
        t_ab.start()
        t_ba.start()
        t_ab.join(timeout=timeout_s)
        t_ba.join(timeout=timeout_s)
    finally:
        for c in (c1, c2):
            try:
                c.close()
            except Exception:
                pass
    return bound


def reverse_dcc_send_via_relay(
    payload: bytes,
    *,
    relay_host: str,
    relay_port: int,
    token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> None:
    """Console role on relay: ROLE then bulk framing (plain TCP to relay)."""
    if len(payload) > DCC_BULK_SIZE_CAP:
        raise ValueError("payload over DCC_BULK_SIZE_CAP")
    sock = socket.create_connection((relay_host, int(relay_port)), timeout=timeout_s)
    try:
        sock.settimeout(timeout_s)
        sock.sendall(f"ROLE console {token}\n".encode("ascii"))
        _write_framed_bulk(sock, payload, token)
        try:
            sock.shutdown(socket.SHUT_WR)
        except Exception:
            pass
    finally:
        sock.close()


def listen_via_relay_receive(
    *,
    relay_host: str,
    relay_port: int,
    expect_token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> tuple[bytes, str]:
    """Caller role on relay: ROLE then read bulk framing + verify sha256."""
    sock = socket.create_connection((relay_host, int(relay_port)), timeout=timeout_s)
    try:
        sock.settimeout(timeout_s)
        sock.sendall(f"ROLE caller {expect_token}\n".encode("ascii"))
        return _read_framed_bulk(sock, expect_token)
    finally:
        sock.close()


def dcclisten_helper_roundtrip(
    payload: bytes,
    *,
    tls: bool = True,
    timeout_s: float = 3.0,
) -> tuple[str, bytes, str]:
    """Bob-ear helper: bind, format DCCLISTEN, accept reverse send, verify sha256.

    Returns ``(dcclisten_line, body, sha256)``.
    """
    token = make_dcc_token()
    job_id = secrets.token_hex(4)
    holder: dict = {}
    port_box: dict = {}
    ready = threading.Event()
    err: list[BaseException] = []

    def _listen2() -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            port_box["port"] = int(srv.getsockname()[1])
            srv.listen(1)
            srv.settimeout(timeout_s)
            tls_ctx = load_tls_server_context() if tls else None
            ready.set()
            try:
                conn, _ = srv.accept()
            finally:
                srv.close()
            try:
                if tls_ctx is not None:
                    conn = tls_ctx.wrap_socket(conn, server_side=True)
                conn.settimeout(timeout_s)
                data, dig = _read_framed_bulk(conn, token)
                holder["data"] = data
                holder["dig"] = dig
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=_listen2, daemon=True)
    t.start()
    if not ready.wait(timeout=timeout_s):
        raise TimeoutError("dcclisten listen not ready")
    port = int(port_box["port"])
    offer = DccListenOffer(
        job_id=job_id,
        host="127.0.0.1",
        port=port,
        token=token,
        tls=tls,
        relay=None,
    )
    line = format_dcclisten(offer)
    reverse_dcc_send(
        payload,
        host="127.0.0.1",
        port=port,
        token=token,
        timeout_s=timeout_s,
        tls=tls,
    )
    t.join(timeout=timeout_s + 1.0)
    if err:
        raise err[0]
    if "data" not in holder:
        raise TimeoutError("dcclisten helper roundtrip failed")
    return line, holder["data"], holder["dig"]


def reverse_dcc_recv(
    *,
    host: str,
    port: int,
    token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
    tls: bool = False,
) -> tuple[bytes, str]:
    """Console connects out and reads a caller-sent framed upload (FR #5194)."""
    raw = socket.create_connection((host, int(port)), timeout=timeout_s)
    sock: socket.socket = raw
    try:
        if tls:
            sni = (
                "localhost"
                if host in {"127.0.0.1", "::1", "localhost"}
                else (host or "localhost")
            )
            sock = load_tls_client_context().wrap_socket(raw, server_hostname=sni)
        sock.settimeout(timeout_s)
        return _read_framed_bulk(sock, token)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def listen_and_send_upload(
    payload: bytes,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    token: str,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
    tls: bool = False,
    ready: threading.Event | None = None,
    port_out: dict | None = None,
) -> int:
    """Caller-side upload: bind, accept console reverse connect, write framed body."""
    if len(payload) > DCC_BULK_SIZE_CAP:
        raise ValueError("payload over DCC_BULK_SIZE_CAP")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(1)
    srv.settimeout(timeout_s)
    bound_port = int(srv.getsockname()[1])
    if port_out is not None:
        port_out["port"] = bound_port
    tls_ctx = load_tls_server_context() if tls else None
    if ready is not None:
        ready.set()
    try:
        conn, _addr = srv.accept()
    finally:
        srv.close()
    try:
        if tls_ctx is not None:
            conn = tls_ctx.wrap_socket(conn, server_side=True)
        conn.settimeout(timeout_s)
        _write_framed_bulk(conn, payload, token)
        try:
            conn.shutdown(socket.SHUT_WR)
        except Exception:
            pass
        return bound_port
    finally:
        try:
            conn.close()
        except Exception:
            pass


def receive_upload_from_offer(
    offer: DccListenOffer,
    *,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> tuple[bytes, str]:
    """Console-side FR #5194: dial the caller DCCLISTEN and read the upload frame."""
    if offer.relay:
        host, _, port_s = offer.relay.partition(":")
        if not host or not port_s:
            raise ValueError("bad relay host:port")
        sock = socket.create_connection((host, int(port_s)), timeout=timeout_s)
        try:
            sock.settimeout(timeout_s)
            sock.sendall(f"ROLE console {offer.token}\n".encode("ascii"))
            return _read_framed_bulk(sock, offer.token)
        finally:
            sock.close()
    return reverse_dcc_recv(
        host=offer.host,
        port=offer.port,
        token=offer.token,
        timeout_s=timeout_s,
        tls=bool(offer.tls),
    )


def upload_roundtrip_localhost(payload: bytes, *, timeout_s: float = 2.0) -> bytes:
    """Test helper: caller listen+send, console recv on localhost."""
    token = make_dcc_token()
    ready = threading.Event()
    port_box: dict = {}
    err: list[BaseException] = []

    def _serve() -> None:
        try:
            listen_and_send_upload(
                payload, token=token, timeout_s=timeout_s, ready=ready, port_out=port_box
            )
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    if not ready.wait(timeout=timeout_s):
        raise TimeoutError("upload listen not ready")
    body, _dig = reverse_dcc_recv(
        host="127.0.0.1",
        port=int(port_box["port"]),
        token=token,
        timeout_s=timeout_s,
    )
    t.join(timeout=timeout_s + 1.0)
    if err:
        raise err[0]
    return body


def send_offer_payload(
    payload: bytes,
    offer: DccListenOffer,
    *,
    timeout_s: float = DCC_HANDSHAKE_TIMEOUT_S,
) -> None:
    """Console-side: honor tls= and relay= on a parsed DCCLISTEN offer (FR #5008)."""
    if offer.relay:
        host, _, port_s = offer.relay.partition(":")
        if not host or not port_s:
            raise ValueError("bad relay host:port")
        reverse_dcc_send_via_relay(
            payload,
            relay_host=host,
            relay_port=int(port_s),
            token=offer.token,
            timeout_s=timeout_s,
        )
        return
    reverse_dcc_send(
        payload,
        host=offer.host,
        port=offer.port,
        token=offer.token,
        timeout_s=timeout_s,
        tls=bool(offer.tls),
    )
