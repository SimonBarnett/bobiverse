"""FR #5659 / #5802: staged + persisted credentials (never on IRC).

Operator flows:
  DCCLISTEN id=<job> ...
  CRED id=<job> via=dcc              # in-memory stage (TLS DCC)
  LEGION host cred=<job>

  CRED id=<job> persist target=PriorityWeb/x via=https url=https://bob.ntsa.uk/...
  # HTTPS pull JSON {username,password} on 443, CredWrite under LocalSystem
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

_CRED_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?CRED(?:\s+(?P<rest>.*))?$"
)
_DEFAULT_TTL_S = 180.0
_HTTPS_FETCH_TIMEOUT_S = 15.0


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
    target = ""
    url = ""
    persist = False
    for part in rest.split():
        low = part.lower()
        if low == "persist":
            persist = True
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        kl = k.lower()
        if kl == "id" and re.fullmatch(r"[0-9a-f]{8}", (v or "").lower()):
            qid = v.lower()
        elif kl == "via":
            via = (v or "").lower()
        elif kl == "target":
            target = (v or "").strip()
        elif kl == "url":
            url = (v or "").strip()
    if rest.lower().find("via=dcc") >= 0:
        via = "dcc"
    if rest.lower().find("via=https") >= 0:
        via = "https"
    return {
        "qid": qid,
        "via": via,
        "target": target,
        "url": url,
        "persist": persist,
        "error": None,
    }


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


def https_cred_url_allowed(url: str, *, env: dict[str, str] | None = None) -> bool:
    """FR #5802: only https:// under fleet public base (or AIRC_CRED_HTTPS_PREFIXES)."""
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if (parsed.scheme or "").lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    prefixes: list[str] = []
    try:
        import bob_public_base as _bpb

        base = _bpb.public_base(env)
        prefixes.append(base.rstrip("/") + "/")
    except Exception:
        prefixes.append("https://bob.ntsa.uk/")
    extra = ""
    src = env if env is not None else None
    if src is None:
        import os

        extra = str(os.environ.get("AIRC_CRED_HTTPS_PREFIXES") or "")
    else:
        extra = str(src.get("AIRC_CRED_HTTPS_PREFIXES") or "")
    for p in extra.split(","):
        p = p.strip()
        if p:
            if not p.endswith("/"):
                p = p + "/"
            prefixes.append(p)
    low = raw.lower()
    for p in prefixes:
        if low.startswith(p.lower()):
            return True
    return False


def classify_https_fetch_error(exc: BaseException) -> str:
    """AV/firewall-aware reason token (never includes URL query secrets)."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http-{int(exc.code)}"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        reason = str(getattr(exc, "reason", "") or exc)
        low = reason.lower()
        if "timed out" in low or "timeout" in low:
            return "timeout"
        if "ssl" in low or "certificate" in low:
            return "ssl-error"
        if "getaddrinfo" in low or "name or service" in low:
            return "dns-failed"
        if "10060" in low or "10061" in low or "actively refused" in low:
            return "firewall-or-unreachable"
        return "firewall-or-unreachable"
    name = type(exc).__name__
    if name in {"TimeoutError", "socket.timeout"}:
        return "timeout"
    return f"https-failed:{name}"


def fetch_cred_json_https(
    url: str,
    *,
    opener: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = _HTTPS_FETCH_TIMEOUT_S,
) -> dict[str, str]:
    """Pull one-shot CRED JSON over HTTPS (443). Password never logged."""
    if not https_cred_url_allowed(url, env=env):
        raise ValueError("cred-url-rejected")
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "bobiverse-airc-cred/1.0", "Accept": "application/json"},
    )
    try:
        with open_fn(req, timeout=float(timeout_s)) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(classify_https_fetch_error(exc)) from exc
    if len(raw) > 64 * 1024:
        raise ValueError("cred-payload-too-large")
    try:
        return parse_cred_json(raw)
    except json.JSONDecodeError as exc:
        # JSONDecodeError subclasses ValueError --- map before generic ValueError.
        raise ValueError("non-json-body") from exc
    except ValueError as exc:
        # Preserve named parse reasons (cred-incomplete / cred-json-object).
        msg = str(exc) or "cred-json-invalid"
        if msg.startswith("cred-"):
            raise
        raise ValueError("cred-json-invalid") from exc
    except Exception as exc:  # noqa: BLE001 - UnicodeDecodeError etc.
        raise ValueError("non-json-body") from exc


def persist_credman(
    target: str,
    username: str,
    password: str,
    *,
    writer: Callable[[str, str, str], None] | None = None,
) -> str:
    """Write LocalSystem CredMan entry; return target (never the secret)."""
    t = (target or "").strip()
    if not t:
        raise ValueError("cred-target-empty")
    write = writer
    if write is None:
        import airc_credman as _cm

        def write(tgt: str, user: str, pw: str) -> None:
            _cm.write_generic_credential(tgt, user, pw)

    try:
        write(t, username, password)
    except Exception as exc:  # noqa: BLE001
        # Prefer CredmanError.reason when present.
        reason = getattr(exc, "reason", None) or type(exc).__name__
        raise ValueError(f"credman-write-failed:{reason}") from exc
    return t
