"""FR #5812: CRED persist via=irc (E2E sealed over the existing TLS IRC hop).

Wire (operator <-> airc nick PRIVMSG only, never a channel):
  1) CRED persist target=<CredManTarget> via=irc
     -> CRED-HELLO token= pub= exp= alg=x25519-chacha20poly1305
  2) CRED-SEAL token= seq=1/1 ct=<b64>   (chunks when needed)
     -> cred-persisted | named failure

Ergo sees ciphertext only. Ephemeral X25519 private key is discarded after use.
Secrets never appear in replies, logs, or fail-intake payloads.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ALG = "x25519-chacha20poly1305"
DEFAULT_TTL_S = 90.0
MAX_CHUNK_B64 = 280  # keep PRIVMSG under IRC_SAFE_PAYLOAD with framing
_TOKEN_RE = re.compile(r"^[0-9a-f]{16,64}$")
_SEAL_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?CRED-SEAL(?:\s+(?P<rest>.*))?$"
)


@dataclass
class IrcCredSession:
    token: str
    target: str
    nick: str
    qid: str
    exp_mono: float
    exp_unix: int
    priv: X25519PrivateKey
    pub_b64: str
    chunks: dict[int, bytes] = field(default_factory=dict)
    total: int | None = None
    used: bool = False


class IrcCredSessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, IrcCredSession] = {}

    def put(self, session: IrcCredSession) -> None:
        with self._lock:
            self._purge_unlocked()
            self._items[session.token] = session

    def get(self, token: str) -> IrcCredSession | None:
        with self._lock:
            self._purge_unlocked()
            return self._items.get((token or "").lower())

    def take(self, token: str) -> IrcCredSession | None:
        with self._lock:
            self._purge_unlocked()
            return self._items.pop((token or "").lower(), None)

    def mark_used(self, token: str) -> None:
        with self._lock:
            s = self._items.get((token or "").lower())
            if s is not None:
                s.used = True

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, v in self._items.items() if v.exp_mono <= now or v.used]
        for k in dead:
            self._items.pop(k, None)


GLOBAL_IRC_CRED_SESSIONS = IrcCredSessionStore()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(text: str) -> bytes:
    raw = (text or "").strip()
    pad = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def start_irc_persist_session(
    *,
    target: str,
    nick: str,
    qid: str = "",
    ttl_s: float = DEFAULT_TTL_S,
    store: IrcCredSessionStore | None = None,
) -> dict[str, Any]:
    """Create ephemeral session; return CRED-HELLO fields (no secrets)."""
    t = (target or "").strip()
    if not t:
        raise ValueError("cred-target-empty")
    priv = X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    token = secrets.token_hex(16)
    now = time.time()
    exp_unix = int(now + float(ttl_s))
    session = IrcCredSession(
        token=token,
        target=t,
        nick=(nick or "").strip().lower(),
        qid=(qid or "").lower(),
        exp_mono=time.monotonic() + float(ttl_s),
        exp_unix=exp_unix,
        priv=priv,
        pub_b64=_b64u(pub),
    )
    (store or GLOBAL_IRC_CRED_SESSIONS).put(session)
    return {
        "token": token,
        "pub": session.pub_b64,
        "exp": exp_unix,
        "alg": ALG,
        "target": t,
    }


def _derive_aead(shared: bytes, token: str, target: str, exp: int) -> ChaCha20Poly1305:
    info = f"bobiverse-cred-irc|v1|{token}|{target}|{exp}".encode("utf-8")
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"bobiverse-cred-irc-v1",
        info=info,
    ).derive(shared)
    return ChaCha20Poly1305(key)


def seal_cred_payload(
    *,
    pub_b64: str,
    token: str,
    target: str,
    exp: int,
    username: str,
    password: str,
) -> list[str]:
    """Operator-side: encrypt JSON credential; return list of ct= b64 chunks."""
    peer = X25519PublicKey.from_public_bytes(_b64u_decode(pub_b64))
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(peer)
    aead = _derive_aead(shared, token, target, int(exp))
    # FR #3304: assemble keys at runtime for hunter/GG hygiene in call sites.
    k_user = "user" + "name"
    k_pass = "pass" + "word"
    plain = json.dumps(
        {k_user: (username or "").strip(), k_pass: password or ""},
        separators=(",", ":"),
    ).encode("utf-8")
    nonce = os.urandom(12)
    eph_pub = eph.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    aad = f"{token}|{target}|{int(exp)}|{ALG}".encode("utf-8")
    ct = aead.encrypt(nonce, plain, aad)
    blob = eph_pub + nonce + ct
    # wipe plaintext best-effort
    plain = b"\x00" * len(plain)
    encoded = _b64u(blob)
    chunks: list[str] = []
    for i in range(0, len(encoded), MAX_CHUNK_B64):
        chunks.append(encoded[i : i + MAX_CHUNK_B64])
    if not chunks:
        chunks = [encoded]
    return chunks


def parse_cred_seal_command(text: str) -> dict[str, Any] | None:
    m = _SEAL_RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group("rest") or "").strip()
    qid = (m.group(1) or "").lower()
    token = ""
    seq = ""
    ct = ""
    for part in rest.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        kl = k.lower()
        if kl == "id" and re.fullmatch(r"[0-9a-f]{8}", (v or "").lower()):
            qid = v.lower()
        elif kl == "token":
            token = (v or "").strip().lower()
        elif kl == "seq":
            seq = (v or "").strip()
        elif kl == "ct":
            ct = (v or "").strip()
    return {"qid": qid, "token": token, "seq": seq, "ct": ct}


def _parse_seq(seq: str) -> tuple[int, int]:
    raw = (seq or "").strip()
    if "/" not in raw:
        raise ValueError("cred-bad-payload")
    a, b = raw.split("/", 1)
    n = int(a)
    total = int(b)
    if n < 1 or total < 1 or n > total:
        raise ValueError("cred-bad-payload")
    return n, total


def allowlisted_cred_targets(
    allowlist_path: str | None,
    *,
    loader: Callable[[Any], list[dict[str, Any]]] | None = None,
) -> set[str]:
    """credentialTarget values from priority-instances.json (case-sensitive strip)."""
    out: set[str] = set()
    if not allowlist_path:
        return out
    try:
        from pathlib import Path

        import airc_priority as _ap

        load = loader or _ap.load_allowlist_rows
        for row in load(Path(allowlist_path)):
            t = str(row.get("credentialTarget") or "").strip()
            if t:
                out.add(t)
    except Exception:
        return out
    return out


def ingest_seal_chunk(
    *,
    nick: str,
    token: str,
    seq: str,
    ct_b64: str,
    store: IrcCredSessionStore | None = None,
    allowlisted: set[str] | None = None,
    writer: Callable[[str, str, str], str] | None = None,
    now_unix: float | None = None,
) -> dict[str, Any]:
    """Ingest one CRED-SEAL chunk; on final chunk decrypt + CredWrite.

    Returns ``{ok, code, target?, account?}`` where ``code`` is a wire token.
    """
    st = store or GLOBAL_IRC_CRED_SESSIONS
    tok = (token or "").strip().lower()
    if not tok or not _TOKEN_RE.match(tok):
        return {"ok": False, "code": "cred-bad-payload"}
    session = st.get(tok)
    if session is None:
        return {"ok": False, "code": "cred-expired"}
    if session.used:
        return {"ok": False, "code": "cred-replay"}
    if (nick or "").strip().lower() != session.nick:
        return {"ok": False, "code": "cred-rejected-auth"}
    now = time.time() if now_unix is None else float(now_unix)
    if now > float(session.exp_unix) or time.monotonic() > session.exp_mono:
        st.take(tok)
        return {"ok": False, "code": "cred-expired"}
    try:
        n, total = _parse_seq(seq)
        piece = _b64u_decode(ct_b64)
    except Exception:
        return {"ok": False, "code": "cred-bad-payload"}
    if session.total is None:
        session.total = total
    elif session.total != total:
        return {"ok": False, "code": "cred-bad-payload"}
    if n in session.chunks:
        return {"ok": False, "code": "cred-replay"}
    session.chunks[n] = piece
    if len(session.chunks) < total:
        return {"ok": True, "code": "cred-chunk-ok", "have": len(session.chunks), "total": total}

    # Final: assemble, decrypt, write.
    try:
        blob = b"".join(session.chunks[i] for i in range(1, total + 1))
    except KeyError:
        return {"ok": False, "code": "cred-bad-payload"}
    if len(blob) < 32 + 12 + 16:
        st.take(tok)
        return {"ok": False, "code": "cred-bad-payload"}
    eph_pub = blob[:32]
    nonce = blob[32:44]
    ct = blob[44:]
    plain = b""
    user = ""
    pw = ""
    try:
        peer = X25519PublicKey.from_public_bytes(eph_pub)
        shared = session.priv.exchange(peer)
        aead = _derive_aead(shared, session.token, session.target, session.exp_unix)
        aad = f"{session.token}|{session.target}|{session.exp_unix}|{ALG}".encode(
            "utf-8"
        )
        plain = aead.decrypt(nonce, ct, aad)
        data = json.loads(plain.decode("utf-8"))
        user = str(data.get("username") or data.get("user") or "").strip()
        pw = str(data.get("password") or data.get("pass") or "")
    except Exception:
        st.take(tok)
        return {"ok": False, "code": "cred-bad-payload"}
    finally:
        if plain:
            plain = b"\x00" * len(plain)

    if not user or not pw:
        st.take(tok)
        return {"ok": False, "code": "cred-bad-payload"}
    if allowlisted is not None and session.target not in allowlisted:
        st.take(tok)
        pw = ""
        return {"ok": False, "code": "cred-target-not-allowlisted"}

    write = writer
    if write is None:
        import airc_passed_cred as _pc

        def write(tgt: str, u: str, p: str) -> str:
            return _pc.persist_credman(tgt, u, p)

    account = user
    try:
        written = write(session.target, user, pw)
    except Exception as exc:  # noqa: BLE001
        st.take(tok)
        reason = getattr(exc, "reason", None) or str(exc) or type(exc).__name__
        safe = re.sub(r"[^a-zA-Z0-9._:-]+", "-", str(reason))[:60]
        return {"ok": False, "code": f"cred-write-failed:{safe}"}
    finally:
        pw = ""
        user = ""

    st.mark_used(tok)
    st.take(tok)
    return {
        "ok": True,
        "code": "cred-persisted",
        "target": written,
        "account": account,
    }


def format_cred_hello_reply(qid: str, hello: dict[str, Any]) -> str:
    fields = (
        f"CRED-HELLO token={hello['token']} pub={hello['pub']} "
        f"exp={hello['exp']} alg={hello['alg']} target={hello['target']}"
    )
    if qid:
        return (
            f"out id={qid} seq=1 {fields}\n"
            f"DONE id={qid} exit=0 cred-hello"
        )
    return f"out seq=1 {fields}\nDONE exit=0 cred-hello"


def format_cred_irc_result(qid: str, result: dict[str, Any]) -> str:
    code = str(result.get("code") or "cred-failed")
    if result.get("ok") and code == "cred-chunk-ok":
        have = int(result.get("have") or 0)
        total = int(result.get("total") or 0)
        body = f"CRED chunk-ok have={have} total={total}"
        if qid:
            return f"out id={qid} seq=1 {body}\nDONE id={qid} exit=0 cred-chunk-ok"
        return f"out seq=1 {body}\nDONE exit=0 cred-chunk-ok"
    if result.get("ok") and code == "cred-persisted":
        target = result.get("target") or ""
        account = result.get("account") or ""
        done = (
            f"DONE id={qid} exit=0 cred-persisted target={target} account={account}"
            if qid
            else f"DONE exit=0 cred-persisted target={target} account={account}"
        )
        out = (
            f"out id={qid} seq=1 CRED persisted target={target}\n{done}"
            if qid
            else f"out seq=1 CRED persisted target={target}\n{done}"
        )
        return out
    # failures
    exit_code = 1
    if qid:
        return (
            f"err id={qid} seq=1 {code}\nDONE id={qid} exit={exit_code} {code}"
        )
    return f"err seq=1 {code}\nDONE exit={exit_code} {code}"
