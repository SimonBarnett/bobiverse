"""Cleartext wire parsers for CAPA / MOOT / FILE / DUMB. Garbage in → None."""
from __future__ import annotations

import re
from dataclasses import dataclass

import seal

MOOT_VERBS = frozenset(
    {"OPEN", "JOIN", "PART", "HANDOFF", "FLOOR", "SAY", "POINT", "YIELD", "ROLL", "ROSTER", "CLOSE"}
)
FILE_VERBS = frozenset({"OFFER", "ACCEPT", "REFUSE", "CHUNK", "DONE", "ABORT"})
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]{1,80}$")
MAX_N_FILE = 320


@dataclass
class CapaLine:
    nick: str
    verbs: str
    psk: str
    agpk: str
    jail: str


@dataclass
class MootLine:
    verb: str
    moot_id: str
    fields: list[str]
    text: str


@dataclass
class FileLine:
    verb: str
    fields: list[str]
    text: str
    chunk_b64: str | None = None
    i: int | None = None
    n: int | None = None
    file_id: str | None = None


def _split_trail(body: str) -> tuple[list[str], str]:
    if " :" in body:
        head, _, trail = body.partition(" :")
        return head.split(), trail
    return body.split(), ""


def parse_capa_line(body: str) -> CapaLine | None:
    parts = body.strip().split()
    if len(parts) < 3 or parts[0] != "CAPA" or parts[1] != "v1" or parts[2] != "dumb":
        return None
    kv: dict[str, str] = {}
    for tok in parts[3:]:
        if "=" not in tok:
            return None
        k, _, v = tok.partition("=")
        kv[k] = v
    if "verbs" not in kv:
        return None
    nick = kv.get("nick", "")
    if nick and not (seal.NICK_RE.match(nick) or re.match(r"^[A-Za-z][A-Za-z0-9._-]{0,31}$", nick)):
        return None
    return CapaLine(nick=nick, verbs=kv.get("verbs", ""), psk=kv.get("psk", ""), agpk=kv.get("agpk", ""), jail=kv.get("jail", ""))


def parse_moot_line(body: str) -> MootLine | None:
    head, text = _split_trail(body.strip())
    if len(head) < 3 or head[0] != "MOOT" or head[1] != "v1":
        return None
    verb = head[2]
    if verb not in MOOT_VERBS:
        return None
    rest = head[3:]
    if not rest:
        return None
    moot_id = rest[0]
    if not seal.MSGID_RE.match(moot_id):
        return None
    fields = rest[1:]
    if any("|" in f for f in fields):
        return None
    if verb == "SAY":
        if len(fields) < 1 or not fields[0].isdigit():
            return None
    if verb == "OPEN":
        if len(fields) != 2 or fields[1] not in {"floor", "free"}:
            return None
        if not (seal.NICK_RE.match(fields[0]) or re.match(r"^[A-Za-z][A-Za-z0-9._-]{0,31}$", fields[0])):
            return None
    return MootLine(verb=verb, moot_id=moot_id, fields=fields, text=text)


def parse_file_line(body: str) -> FileLine | None:
    head, text = _split_trail(body.strip())
    if len(head) < 3 or head[0] != "FILE" or head[1] != "v1":
        return None
    verb = head[2]
    if verb not in FILE_VERBS:
        return None
    rest = head[3:]
    if verb == "CHUNK":
        if len(rest) != 4:
            return None
        fid, i_s, n_s, b64 = rest
        if not seal.MSGID_RE.match(fid):
            return None
        if not n_s.isdigit() or len(n_s) > 3 or not i_s.isdigit() or len(i_s) > 3:
            return None
        n, i = int(n_s), int(i_s)
        if n < 1 or n > MAX_N_FILE or i < 1 or i > n:
            return None
        return FileLine(verb=verb, fields=rest, text=text, chunk_b64=b64, i=i, n=n, file_id=fid)
    if verb == "OFFER":
        if len(rest) != 7:
            return None
        to_n, from_n, fid = rest[0], rest[1], rest[2]
        if fid.startswith(".") or "/" in fid or "\\" in fid or ".." in fid:
            return None
        if not seal.MSGID_RE.match(fid):
            return None
        name = rest[-1]
        if "/" in name or "\\" in name or " " in name or not FILE_NAME_RE.match(name):
            return None
        if from_n != "*" and not seal.NICK_RE.match(from_n):
            return None
        if to_n != "*" and not seal.NICK_RE.match(to_n):
            return None
        return FileLine(verb=verb, fields=rest, text=text, file_id=fid)
    if not rest or not seal.MSGID_RE.match(rest[0]):
        return None
    return FileLine(verb=verb, fields=rest, text=text, file_id=rest[0])


def parse_dumb_line(body: str) -> seal.SealLine | None:
    """DUMB v1 <to> <from> <id> <i> <n> <b64> — same shape as SEAL v2."""
    text = body.strip()
    if not text.startswith("DUMB v1 "):
        return None
    fake = "SEAL v2 " + text[len("DUMB v1 ") :]
    return seal.parse_seal_line(fake)
