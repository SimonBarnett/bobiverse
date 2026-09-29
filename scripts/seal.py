#!/usr/bin/env python3
"""X25519 boxes for agentic IRC.

v1: anonymous sealed box (eph X25519 + HKDF + AES-GCM). Keep a parser; do not send.
v2: TOFU-pinned DH-AAD (not a signature). Blob = sender_pk(32) || eph_pk(32) || nonce(12) || ct+tag.
    AAD = lower(channel)|lower(to)|lower(from)|lower(id). No '|' in fields.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protect  # noqa: E402

INFO_V1 = b"agentic-irc-seal-v1"
INFO_V2 = b"agentic-irc-seal-v2"
INFO_DUMB = b"dumb-v1"
CHUNK = 300
MAX_N = 64
BAG_TTL_S = 120.0
MAX_INDEX_DIGITS = 2  # n <= 64
MSGID_RE = re.compile(r"^[a-fA-F0-9]{16}$")
NICK_RE = re.compile(r"^[A-Za-z\[\]^`{|}][A-Za-z0-9\[\]^`{|_-]{0,31}$")
def home() -> Path:
    raw = os.environ.get("AGENTIC_IRC_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".agentic-irc"


def ident_path() -> Path:
    return home() / "identity.json"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def genkey(path: Path | None = None) -> dict:
    path = path or ident_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protect.protect_path(path.parent)
    if path.exists():
        raise SystemExit(f"identity already exists: {path}")
    sk = X25519PrivateKey.generate()
    pk = sk.public_key()
    doc = {
        "v": 1,
        "sk": b64(sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )),
        "pk": b64(pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )),
    }
    protect.write_secret_bytes(path, (json.dumps(doc) + "\n").encode("utf-8"))
    return doc


def load_ident(path: Path | None = None) -> dict:
    path = path or ident_path()
    if not path.exists():
        raise SystemExit(f"no identity at {path}; run: python scripts/seal.py genkey")
    return json.loads(protect.read_secret_bytes(path).decode("utf-8"))


def _raw_sk(ident: dict) -> X25519PrivateKey:
    return X25519PrivateKey.from_private_bytes(b64d(ident["sk"]))


def _raw_pk(b64pk: str) -> X25519PublicKey:
    return X25519PublicKey.from_public_bytes(b64d(b64pk))


def _pub_bytes(pk: X25519PublicKey) -> bytes:
    return pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)


def aad_v2(channel: str, to_nick: str, from_nick: str, msg_id: str) -> bytes:
    fields = (channel, to_nick, from_nick, msg_id)
    if any("|" in f for f in fields):
        raise ValueError("pipe in AAD field")
    ch, to, fr, mid = (f.lower() for f in fields)
    return f"{ch}|{to}|{fr}|{mid}".encode("utf-8")


def dumb_aad(channel: str, to_nick: str, from_nick: str, msg_id: str) -> bytes:
    return f"{channel.lower()}|{to_nick.lower()}|{from_nick.lower()}|{msg_id.lower()}|dumb-v1".encode()


def dumb_seal_bytes(plaintext: bytes, key32: bytes, channel: str, to_nick: str, from_nick: str, msg_id: str) -> bytes:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key32).encrypt(nonce, plaintext, dumb_aad(channel, to_nick, from_nick, msg_id))
    return nonce + ct


def dumb_open_bytes(blob: bytes, key32: bytes, channel: str, to_nick: str, from_nick: str, msg_id: str) -> bytes:
    if len(blob) < 12 + 16:
        raise ValueError("ciphertext too short")
    return AESGCM(key32).decrypt(blob[:12], blob[12:], dumb_aad(channel, to_nick, from_nick, msg_id))


def dumb_irc_lines(blob: bytes, to_nick: str, from_nick: str, msg_id: str | None = None) -> list[str]:
    payload = b64(blob)
    parts = [payload[i : i + CHUNK] for i in range(0, len(payload), CHUNK)] or [""]
    n = len(parts)
    if n > MAX_N:
        raise ValueError("too many chunks")
    msg_id = msg_id or secrets.token_hex(8)
    return [f"DUMB v1 {to_nick} {from_nick} {msg_id} {i + 1} {n} {part}" for i, part in enumerate(parts)]


def seal_bytes_v1(plaintext: bytes, recip_pk_b64: str) -> bytes:
    eph = X25519PrivateKey.generate()
    recip = _raw_pk(recip_pk_b64)
    shared = eph.exchange(recip)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO_V1).derive(shared)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, INFO_V1)
    return _pub_bytes(eph.public_key()) + nonce + ct


def open_bytes_v1(blob: bytes, ident: dict) -> bytes:
    if len(blob) < 32 + 12 + 16:
        raise ValueError("ciphertext too short")
    eph_pk = X25519PublicKey.from_public_bytes(blob[:32])
    nonce, ct = blob[32:44], blob[44:]
    shared = _raw_sk(ident).exchange(eph_pk)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO_V1).derive(shared)
    return AESGCM(key).decrypt(nonce, ct, INFO_V1)


def seal_bytes_v2(
    plaintext: bytes,
    recip_pk_b64: str,
    ident: dict,
    channel: str,
    to_nick: str,
    from_nick: str,
    msg_id: str,
) -> bytes:
    sender_sk = _raw_sk(ident)
    sender_pk = _pub_bytes(sender_sk.public_key())
    recip = _raw_pk(recip_pk_b64)
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(recip) + sender_sk.exchange(recip)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sender_pk + _pub_bytes(recip),
        info=INFO_V2,
    ).derive(shared)
    nonce = secrets.token_bytes(12)
    aad = aad_v2(channel, to_nick, from_nick, msg_id)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return sender_pk + _pub_bytes(eph.public_key()) + nonce + ct


def open_bytes_v2(
    blob: bytes,
    ident: dict,
    channel: str,
    to_nick: str,
    from_nick: str,
    msg_id: str,
    expected_sender_pk_b64: str,
) -> bytes:
    if len(blob) < 32 + 32 + 12 + 16:
        raise ValueError("ciphertext too short")
    sender_pk, eph_raw, nonce, ct = blob[:32], blob[32:64], blob[64:76], blob[76:]
    if b64(sender_pk) != expected_sender_pk_b64:
        raise ValueError("sender key does not match pinned AGPK")
    recip_sk = _raw_sk(ident)
    eph_pk = X25519PublicKey.from_public_bytes(eph_raw)
    sender = X25519PublicKey.from_public_bytes(sender_pk)
    shared = recip_sk.exchange(eph_pk) + recip_sk.exchange(sender)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sender_pk + _pub_bytes(recip_sk.public_key()),
        info=INFO_V2,
    ).derive(shared)
    aad = aad_v2(channel, to_nick, from_nick, msg_id)
    return AESGCM(key).decrypt(nonce, ct, aad)


# Back-compat names used by older tests / v1 open
def seal_bytes(plaintext: bytes, recip_pk_b64: str) -> bytes:
    return seal_bytes_v1(plaintext, recip_pk_b64)


def open_bytes(blob: bytes, ident: dict) -> bytes:
    return open_bytes_v1(blob, ident)


def irc_lines_v2(
    blob: bytes,
    to_nick: str,
    from_nick: str,
    msg_id: str | None = None,
) -> list[str]:
    payload = b64(blob)
    parts = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [""]
    n = len(parts)
    if n > MAX_N:
        raise ValueError(f"payload needs {n} chunks; max {MAX_N}")
    msg_id = msg_id or secrets.token_hex(8)
    return [f"SEAL v2 {to_nick} {from_nick} {msg_id} {i + 1} {n} {part}" for i, part in enumerate(parts)]


def irc_lines(blob: bytes, to_nick: str, msg_id: str | None = None) -> list[str]:
    """v1 wire (legacy). Prefer irc_lines_v2."""
    payload = b64(blob)
    parts = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [""]
    n = len(parts)
    if n > MAX_N:
        raise ValueError(f"payload needs {n} chunks; max {MAX_N}")
    msg_id = msg_id or secrets.token_hex(8)
    return [f"SEAL v1 {to_nick} {msg_id} {i + 1} {n} {part}" for i, part in enumerate(parts)]


@dataclass
class SealLine:
    version: int
    to_nick: str
    from_nick: str | None
    msg_id: str
    i: int
    n: int
    chunk: str


def _parse_index(s: str) -> int | None:
    if not s.isdigit() or len(s) > MAX_INDEX_DIGITS:
        return None
    v = int(s)
    if v < 1 or v > MAX_N:
        return None
    return v


def parse_seal_line(line: str) -> SealLine | None:
    text = line.strip()
    if not text.startswith("SEAL "):
        return None
    bits = text.split(" ")
    if len(bits) < 7:
        return None
    ver = bits[1]
    if ver == "v1":
        if len(bits) != 7:
            return None
        _, _, to_nick, msg_id, i_s, n_s, chunk = bits
        from_nick = None
        version = 1
    elif ver == "v2":
        if len(bits) != 8:
            return None
        _, _, to_nick, from_nick, msg_id, i_s, n_s, chunk = bits
        version = 2
    else:
        return None
    i = _parse_index(i_s)
    n = _parse_index(n_s)
    if i is None or n is None or i > n:
        return None
    if not MSGID_RE.match(msg_id) or not NICK_RE.match(to_nick):
        return None
    if from_nick is not None and not NICK_RE.match(from_nick):
        return None
    return SealLine(version, to_nick, from_nick, msg_id, i, n, chunk)


def parse_agpk_line(body: str) -> str | None:
    if not body.startswith("AGPK v1 "):
        return None
    pk = body[8:].strip()
    try:
        raw = b64d(pk)
    except Exception:
        return None
    if len(raw) != 32:
        return None
    return b64(raw)


class FragmentStore:
    """Reassemble SEAL chunks. Caps n, TTL, rejects dup i / out of range before allocating."""

    def __init__(self, ttl_s: float = BAG_TTL_S) -> None:
        self.ttl_s = ttl_s
        self._bags: dict[str, dict] = {}

    def _gc(self, now: float) -> None:
        dead = [k for k, b in self._bags.items() if now - b["t0"] > self.ttl_s]
        for k in dead:
            del self._bags[k]

    def add(self, line: SealLine, now: float | None = None) -> str | None:
        """Return concatenated b64 when complete, else None. Never allocates n>MAX_N slots."""
        now = time.time() if now is None else now
        self._gc(now)
        if line.n > MAX_N or line.i < 1 or line.i > line.n:
            return None
        key = ((line.from_nick or "").lower(), line.msg_id.lower())
        bag = self._bags.get(key)
        if bag is None:
            bag = {"n": line.n, "ver": line.version, "parts": {}, "t0": now}
            self._bags[key] = bag
        if bag["n"] != line.n or bag["ver"] != line.version:
            return None
        prev = bag["parts"].get(line.i)
        if prev is not None and prev != line.chunk:
            del self._bags[key]
            return None
        bag["parts"][line.i] = line.chunk
        if len(bag["parts"]) < line.n:
            return None
        payload = "".join(bag["parts"][j] for j in range(1, line.n + 1))
        del self._bags[key]
        return payload


def load_peers(path: Path | None = None) -> dict:
    path = path or (home() / "peers.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Unreadable (ACL from protect.protect_path under another token) or corrupt:
        # start with no TOFU peers rather than crash-looping the seat (2026-09-25).
        return {}


def save_peers(peers: dict, path: Path | None = None) -> None:
    path = path or (home() / "peers.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(peers, indent=2) + "\n", encoding="utf-8")
    protect.protect_path(path)


def tofu_pin(peers: dict, nick: str, pk_b64: str) -> str:
    """Return 'ok', 'pinned', or 'mismatch'."""
    rec = peers.get(nick.lower())
    if rec is None:
        peers[nick.lower()] = {"pk": pk_b64, "nick": nick}
        return "pinned"
    if rec.get("pk") != pk_b64:
        return "mismatch"
    return "ok"


def main() -> None:
    p = argparse.ArgumentParser(description="agentic-irc sealed box")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("genkey", help="create identity (DPAPI on Windows)")
    sub.add_parser("pubkey", help="print AGPK v1 line for IRC")
    dk = sub.add_parser("dumb-key", help="write 32-byte connector.key (fingerprint on stderr)")
    dk.add_argument("--home", default="")

    sp = sub.add_parser("seal", help="encrypt to SEAL v2 IRC lines")
    sp.add_argument("--to", required=True, help="recipient X25519 public key (base64)")
    sp.add_argument("--nick", dest="to_nick", required=True, help="recipient IRC nick (not self)")
    sp.add_argument("--from-nick", required=True, help="your IRC nick")
    sp.add_argument("--channel", required=True, help="channel bound into AAD, e.g. #ops")
    sp.add_argument("--in", dest="infile", default="-", help="plaintext file or -")

    op = sub.add_parser("open", help="decrypt a complete blob (v1 or v2)")
    op.add_argument("--in", dest="infile", default="-")
    op.add_argument("--out", dest="outfile", default="-")
    op.add_argument("--v2", action="store_true")
    op.add_argument("--channel", default="")
    op.add_argument("--to-nick", default="")
    op.add_argument("--from-nick", default="")
    op.add_argument("--id", dest="msg_id", default="")
    op.add_argument("--sender-pk", default="")

    args = p.parse_args()
    if args.cmd == "genkey":
        doc = genkey()
        print(f"wrote {ident_path()}", file=sys.stderr)
        print(f"AGPK v1 {doc['pk']}")
        return
    if args.cmd == "pubkey":
        print(f"AGPK v1 {load_ident()['pk']}")
        return
    if args.cmd == "dumb-key":
        if args.home:
            os.environ["AGENTIC_IRC_HOME"] = str(Path(args.home).expanduser())
        d = home() / "dumb"
        d.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        dest = d / "connector.key"
        protect.write_secret_bytes(dest, key)
        import hashlib
        print(hashlib.sha256(key).hexdigest(), file=sys.stderr)
        return
    if args.cmd == "seal":
        if "|" in args.channel or "|" in args.to_nick or "|" in args.from_nick:
            raise SystemExit("channel and nicks must not contain |")
        data = sys.stdin.buffer.read() if args.infile == "-" else Path(args.infile).read_bytes()
        ident = load_ident()
        msg_id = secrets.token_hex(8)
        blob = seal_bytes_v2(
            data, args.to, ident, args.channel, args.to_nick, args.from_nick, msg_id
        )
        for line in irc_lines_v2(blob, args.to_nick, args.from_nick, msg_id):
            print(line)
        return
    if args.cmd == "open":
        raw = sys.stdin.buffer.read() if args.infile == "-" else Path(args.infile).read_bytes()
        try:
            blob = b64d(raw.decode("ascii").replace("\n", "").replace(" ", ""))
        except Exception:
            blob = raw
        ident = load_ident()
        if args.v2:
            pt = open_bytes_v2(
                blob, ident, args.channel, args.to_nick, args.from_nick, args.msg_id, args.sender_pk
            )
        else:
            pt = open_bytes_v1(blob, ident)
        if args.outfile == "-":
            sys.stdout.buffer.write(pt)
        else:
            Path(args.outfile).write_bytes(pt)
            protect.protect_path(Path(args.outfile))


if __name__ == "__main__":
    main()
