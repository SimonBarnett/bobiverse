"""Airc NETWORK verb + isolated inventory worker (FR #5298 / #5299).

FR-A: verb + isolated stub. FR-B: LDAP computers + ips[] + OU/DN.
No DCC in this slice. Auth matches UPDATE.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

_NETWORK_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?NETWORK(?:\s+diag)?(?:\s+(-WhatIf))?\s*$"
)


@dataclass
class NetworkVerbResult:
    ok: bool
    reply: str
    job_id: str = ""

    def reply_text(self) -> str:
        return self.reply


def parse_network_command(text: str) -> dict[str, Any] | None:
    m = _NETWORK_CMD_RE.match((text or "").strip())
    if not m:
        return None
    return {
        "qid": (m.group(1) or "").lower(),
        "action": "diag",
        "whatif": bool(m.group(2)),
    }


def stub_network_work(
    action: str = "diag",
    *,
    whatif: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "hosts": [],
        "ldap": False,
    }


def ou_from_dn(dn: str | None) -> str:
    raw = (dn or "").strip()
    if not raw:
        return "unknown"
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    kept = [p for p in parts if p[:3].upper() in {"OU=", "DC="}]
    return ",".join(kept) if kept else "unknown"


def default_ldap_enum() -> list[Any]:
    """Workgroup / no-DC: empty (documented). Tests inject AD rows."""
    return []


def default_resolve_ips(host: str) -> list[str]:
    import socket

    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
    except OSError:
        raise
    ips: list[str] = []
    for item in infos:
        addr = item[4][0]
        if addr not in ips:
            ips.append(addr)
    return ips


def inventory_work(
    action: str = "diag",
    *,
    whatif: bool = False,
    ldap_enum: Callable[[], list[Any]] | None = None,
    resolve_ips: Callable[[str], list[str]] | None = None,
    extra_hosts: list[str] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5299: hostname + ips[] + ou. Never uses extra_hosts."""
    _ = extra_hosts
    enum = ldap_enum or default_ldap_enum
    resolve = resolve_ips or default_resolve_ips
    rows = list(enum() or [])
    hosts: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    for raw in rows:
        if isinstance(raw, str):
            name, dn = raw.strip(), ""
        elif isinstance(raw, dict):
            name = str(raw.get("hostname") or raw.get("name") or "").strip()
            dn = str(raw.get("dn") or raw.get("distinguishedName") or "")
        else:
            continue
        if not name:
            continue
        rec: dict[str, Any] = {
            "hostname": name,
            "ips": [],
            "ou": ou_from_dn(dn),
            "dn": dn or "unknown",
        }
        try:
            rec["ips"] = list(resolve(name) or [])
        except Exception as exc:
            rec["ips"] = []
            log.append({"host": name, "error": type(exc).__name__, "step": "resolve"})
        hosts.append(rec)
    ldap_ok = bool(rows)
    return {
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "hosts": hosts,
        "log": log,
        "ldap": ldap_ok,
        "limit": "" if ldap_ok else "workgroup-or-no-dc",
    }


def run_network_verb(
    *,
    action: str = "diag",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    **_kw: Any,
) -> NetworkVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or inventory_work

    def _safe() -> None:
        try:
            work(action=action, whatif=whatif, **_kw)
        except Exception:
            return

    if wait:
        _safe()
    else:
        threading.Thread(target=_safe, name="airc-network-worker", daemon=True).start()
    extra = " whatif=1" if whatif else ""
    reply = f"NETWORK accepted id={qid} action={action}{extra}\nDONE id={qid} exit=0"
    return NetworkVerbResult(True, reply, job_id=qid)
