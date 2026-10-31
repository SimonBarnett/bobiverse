"""Airc NETWORK verb + isolated inventory worker (FR #5298 / #5299 / #5300).

FR-A: verb + isolated stub. FR-B: LDAP computers + ips[] + OU/DN.
FR-C: structured inventory+log via DCCLISTEN or IRC CONT. Auth matches UPDATE.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

_NETWORK_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?NETWORK(?:\s+diag)?(?:\s+(-WhatIf))?\s*$"
)


@dataclass
class NetworkVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    hosts: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

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
    """AD computers via LDAP/ADSI (hostname + distinguishedName).

    FR #5521: NETWORK diag must not stub ``[]`` on a domain-joined console.
    Empty when not Windows, PowerShell missing, or DC/ADSI unavailable
    (workgroup / no-DC path — never invent hosts).
    """
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return []
    # Pair lines N=<name> / D=<distinguishedName> (ADSI Properties keys are lower).
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=[adsisearcher]'(objectCategory=computer)';"
        "$s.PageSize=500;"
        "[void]$s.PropertiesToLoad.Add('name');"
        "[void]$s.PropertiesToLoad.Add('distinguishedName');"
        "foreach($r in $s.FindAll()){"
        "$n=$null;$d=$null;"
        "if($r.Properties['name'] -and $r.Properties['name'].Count -gt 0){$n=$r.Properties['name'][0]};"
        "if($r.Properties['distinguishedname'] -and $r.Properties['distinguishedname'].Count -gt 0){"
        "$d=$r.Properties['distinguishedname'][0]};"
        "if($n){Write-Output ('N='+[string]$n);Write-Output ('D='+[string]$d)}"
        "}"
    )
    try:
        p = subprocess.run(
            [ps, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return []
    if p.returncode != 0:
        return []
    rows: list[dict[str, str]] = []
    cur_name = ""
    cur_dn = ""
    for line in (p.stdout or "").splitlines():
        raw = line.strip()
        if raw.startswith("N="):
            if cur_name:
                rows.append({"hostname": cur_name, "dn": cur_dn})
            cur_name = raw[2:].strip()
            cur_dn = ""
        elif raw.startswith("D="):
            cur_dn = raw[2:].strip()
    if cur_name:
        rows.append({"hostname": cur_name, "dn": cur_dn})
    return rows


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
    on_done: Callable[[NetworkVerbResult], Any] | None = None,
    **_kw: Any,
) -> NetworkVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or inventory_work
    extra = " whatif=1" if whatif else ""
    # FR #5583: accept only; DONE is last after out/CONT from deliver_*.
    accepted = f"NETWORK accepted id={qid} action={action}{extra}"

    def _finish(data: dict[str, Any]) -> NetworkVerbResult:
        hosts = list(data.get("hosts") or [])
        failures = list(data.get("failures") or data.get("log") or [])
        res = NetworkVerbResult(
            bool(data.get("ok", True)),
            accepted,
            job_id=qid,
            hosts=hosts,
            failures=failures,
        )
        if on_done is not None:
            on_done(res)
        return res

    def _safe() -> NetworkVerbResult:
        try:
            data = work(action=action, whatif=whatif, **_kw)
            if not isinstance(data, dict):
                data = {"ok": True, "hosts": [], "log": []}
        except Exception as exc:
            data = {
                "ok": False,
                "hosts": [],
                "log": [{"error": type(exc).__name__, "step": "worker"}],
            }
        return _finish(data)

    if wait:
        return _safe()
    import airc_isolated as _iso

    if _iso.is_packaged_work(work):

        def _from_child(data: Any) -> None:
            payload = data if isinstance(data, dict) else {
                "ok": False,
                "hosts": [],
                "log": [{"error": "isolated-fault", "step": "worker"}],
            }
            _finish(payload)

        _iso.start_isolated(
            wait=False,
            run=_safe,
            packaged=(
                "airc_network",
                "inventory_work",
                {"action": action, "whatif": bool(whatif)},
            ),
            name="airc-network-worker",
            on_done=_from_child,
        )
    else:
        threading.Thread(target=_safe, name="airc-network-worker", daemon=True).start()
    return NetworkVerbResult(True, accepted, job_id=qid)


_SECRET_KEY_RE = re.compile(r"(?i)pass|secret|token|pwd|cred")


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _scrub(v)
            for k, v in obj.items()
            if not _SECRET_KEY_RE.search(str(k))
        }
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str) and _SECRET_KEY_RE.search(obj) and "=" in obj:
        return "[redacted]"
    return obj


def build_network_payload(
    action: str = "diag",
    *,
    whatif: bool = False,
    hosts: list[dict] | None = None,
    failures: list[dict] | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    """FR #5300: inventory hosts[] plus operation failures[]; secrets stripped."""
    payload: dict[str, Any] = {
        "action": action,
        "whatif": bool(whatif),
        "hosts": list(hosts or []),
        "failures": list(failures or []),
    }
    if extra:
        for k, v in extra.items():
            if not _SECRET_KEY_RE.search(str(k)):
                payload[k] = v
    payload = _scrub(payload)
    payload["host_count"] = len(payload.get("hosts") or [])
    payload["failure_count"] = len(payload.get("failures") or [])
    return payload


def network_payload_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def deliver_network_payload(
    *,
    job_id: str,
    payload: dict[str, Any],
    offer: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    import airc_dcc_bulk as _dcc

    jid = (job_id or "").strip().lower() or "00000000"
    raw = network_payload_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    nfail = int(payload.get("failure_count") or 0)
    nhost = int(payload.get("host_count") or 0)
    summary = (
        f"NETWORK log hosts={nhost} failures={nfail} "
        f"action={payload.get('action')} bytes={len(raw)}"
    )
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(payload.get("failures") or [], start=2):
        lines.append(
            f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}"
        )
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(
                jid, 0, nbytes=len(raw), sha256=digest, via="dcc"
            )
            return {
                "via": "dcc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": [lines[0], done],
                "done": done,
            }
        except Exception as exc:
            lines.append(
                f"err id={jid} seq={len(lines)+1} dcc failed: {exc}; falling back to IRC"
            )
            lines.append("CONT id=" + jid + " offset=1")
            done = f"DONE id={jid} exit=0 via=irc reason=dcc-fail"
            lines.append(done)
            return {
                "via": "irc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": lines,
                "done": done,
                "payload": raw,
            }
    lines.append("CONT id=" + jid + " offset=1")
    done = f"DONE id={jid} exit=0 via=irc"
    lines.append(done)
    return {
        "via": "irc",
        "sha256": digest,
        "nbytes": len(raw),
        "summary": summary,
        "lines": lines,
        "done": done,
        "payload": raw,
    }
