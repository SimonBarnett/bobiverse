"""FR #5659: short-lived in-memory credentials staged over TLS DCC only.

IRC must never carry the password. Operator flow:
  DCCLISTEN id=<job> ...
  CRED id=<job> via=dcc   # console reads JSON {username,password} over DCC
  LEGION host cred=<job>  # or EXTENSION ... cred=<job>
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

_CRED_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?CRED(?:\s+(?P<rest>.*))?$"
)
_DEFAULT_TTL_S = 180.0


@dataclass
class StagedCred:
    username: str
    password: str
    expires_at: float
    job_id: str


class PassedCredStore:
    """Process-local one-shot credential stash (never written to disk)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, StagedCred] = {}

    def put(
        self,
        job_id: str,
        username: str,
        password: str,
        *,
        ttl_s: float = _DEFAULT_TTL_S,
    ) -> None:
        jid = (job_id or "").strip().lower()
        user = (username or "").strip()
        pw = password or ""
        if not jid or not user or not pw:
            raise ValueError("cred-incomplete")
        with self._lock:
            self._purge_unlocked()
            self._items[jid] = StagedCred(
                username=user,
                password=pw,
                expires_at=time.monotonic() + float(ttl_s),
                job_id=jid,
            )

    def peek(self, job_id: str) -> dict[str, str] | None:
        jid = (job_id or "").strip().lower()
        with self._lock:
            self._purge_unlocked()
            item = self._items.get(jid)
            if item is None:
                return None
            return {"username": item.username, "password": item.password}

    def take(self, job_id: str) -> dict[str, str] | None:
        jid = (job_id or "").strip().lower()
        with self._lock:
            self._purge_unlocked()
            item = self._items.pop(jid, None)
            if item is None:
                return None
            return {"username": item.username, "password": item.password}

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, v in self._items.items() if v.expires_at <= now]
        for k in dead:
            self._items.pop(k, None)


GLOBAL_PASSED_CREDS = PassedCredStore()


def parse_cred_command(text: str) -> dict[str, Any] | None:
    m = _CRED_RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group("rest") or "").strip()
    qid = (m.group(1) or "").lower()
    via = ""
    for part in rest.split():
        if "=" in part:
            k, v = part.split("=", 1)
            if k.lower() == "id" and re.fullmatch(r"[0-9a-f]{8}", v.lower() or ""):
                qid = v.lower()
            elif k.lower() == "via":
                via = v.lower()
        elif part.lower() == "via=dcc":
            via = "dcc"
    if rest.lower().find("via=dcc") >= 0:
        via = "dcc"
    return {"qid": qid, "via": via, "error": None}


def parse_cred_json(raw: bytes | str) -> dict[str, str]:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = raw
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("cred-json-object")
    user = str(data.get("username") or data.get("user") or "").strip()
    pw = str(data.get("password") or data.get("pass") or "")
    if not user or not pw:
        raise ValueError("cred-incomplete")
    return {"username": user, "password": pw}


def extract_cred_ref(rest: str) -> tuple[str, str]:
    """Pull cred=<8hex> from a verb rest string; return (cred_id, rest_without)."""
    cred_id = ""
    parts: list[str] = []
    for part in (rest or "").split():
        m = re.match(r"(?i)^cred=([0-9a-f]{8})$", part)
        if m:
            cred_id = m.group(1).lower()
            continue
        parts.append(part)
    return cred_id, " ".join(parts)
