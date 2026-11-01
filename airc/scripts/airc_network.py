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
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?NETWORK(?:\s+(.*))?$"
)
NETWORK_USAGE = "[diag] [-WhatIf] [cred=<8hex>]"


@dataclass
class NetworkVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    hosts: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    identity: dict[str, Any] = field(default_factory=dict)

    def reply_text(self) -> str:
        return self.reply


def parse_network_command(text: str) -> dict[str, Any] | None:
    m = _NETWORK_CMD_RE.match((text or "").strip())
    if not m:
        return None
    qid = (m.group(1) or "").lower()
    import airc_identity as _ident
    import airc_passed_cred as _pcred

    rest = m.group(2) or ""
    if _ident.irc_line_has_plaintext_secret(rest):
        return {"qid": qid, "usage": True, "unknown_flag": "secrets-on-irc"}
    cred_id, rest = _pcred.extract_cred_ref(rest)
    tokens = [(t or "").strip() for t in rest.split() if t.strip()]
    whatif = False
    extra = False
    unknown = ""
    for tok in tokens:
        low = tok.lower()
        if low == "diag":
            continue
        if low == "-whatif":
            whatif = True
            continue
        if tok.startswith("-"):
            unknown = tok
            break
        extra = True
    if unknown:
        return {"qid": qid, "usage": True, "unknown_flag": unknown}
    if extra:
        return {"qid": qid, "usage": True}
    return {
        "qid": qid,
        "action": "diag",
        "whatif": whatif,
        "cred_id": cred_id,
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
    """Parent container DN (strip leaf RDN). FR #5587: keep CN=Computers etc.

    Splits on the first unescaped comma (even-length backslash run before it).
    Empty / single-RDN / no parent -> ``unknown``.
    """
    raw = (dn or "").strip()
    if not raw:
        return "unknown"
    i = 0
    while i < len(raw):
        if raw[i] == ",":
            n = 0
            j = i - 1
            while j >= 0 and raw[j] == "\\":
                n += 1
                j -= 1
            if n % 2 == 0:
                parent = raw[i + 1 :].strip()
                return parent if parent else "unknown"
        i += 1
    return "unknown"


def default_ldap_enum(*, identity: Any = None) -> list[Any]:
    """AD computers via LDAP/ADSI (hostname + distinguishedName).

    FR #5521: NETWORK diag must not stub ``[]`` on a domain-joined console.
    Empty when not Windows, PowerShell missing, or DC/ADSI unavailable
    (workgroup / no-DC path — never invent hosts).
    """
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        if identity is not None and identity.source != "system":
            raise RuntimeError("ldap_failed")
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        if identity is not None and identity.source != "system":
            raise RuntimeError("ldap_failed")
        return []
    # Pair lines N=<name> / D=<distinguishedName> (ADSI Properties keys are lower).
    bind = "$s=[adsisearcher]'(objectCategory=computer)';"
    explicit = identity is not None and identity.source != "system"
    if explicit:
        bind = (
            "$c=[Console]::In.ReadToEnd()|ConvertFrom-Json;"
            "$root=[System.DirectoryServices.DirectoryEntry]::new("
            "'LDAP://RootDSE',[string]$c.username,[string]$c.password);"
            "$dn=[string]$root.Properties['defaultNamingContext'][0];"
            "$base=[System.DirectoryServices.DirectoryEntry]::new("
            "('LDAP://'+$dn),[string]$c.username,[string]$c.password);"
            "$s=[System.DirectoryServices.DirectorySearcher]::new($base);"
            "$s.Filter='(objectCategory=computer)';"
        )
    script = (
        "$ErrorActionPreference='Stop';"
        + bind +
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
            **({"input": json.dumps({
                "username": identity.username, "password": identity.password,
            })} if explicit else {}),
        )
    except Exception:
        if explicit:
            raise RuntimeError("ldap_failed") from None
        return []
    if p.returncode != 0:
        if explicit:
            # Never echo PowerShell errors: credentials may be present in diagnostics.
            raise RuntimeError("auth_failed") from None
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
    passed_cred: dict[str, str] | None = None,
    passed_requested: bool = False,
    credman_reader: Callable[..., Any] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5299: hostname + ips[] + ou. Never uses extra_hosts."""
    _ = extra_hosts
    import airc_identity as _ident

    if passed_requested and not (
        passed_cred and passed_cred.get("username") and passed_cred.get("password")
    ):
        return {
            "ok": False, "hosts": [], "identity": "passed", "account": "",
            "failures": [{"step": "identity", "error": "auth_failed"}],
        }
    identity = _ident.resolve_remote_identity(
        verb="network", passed=passed_cred, credman_reader=credman_reader,
    )
    public = identity.public_dict()
    resolve = resolve_ips or default_resolve_ips
    try:
        rows = list(
            (ldap_enum() if ldap_enum else default_ldap_enum(identity=identity)) or []
        )
    except Exception as exc:
        return {
            **public, "ok": False, "hosts": [], "ldap": False,
            "failures": [{
                "step": "ldap",
                "error": "auth_failed" if str(exc) == "auth_failed" else "ldap_failed",
            }],
        }
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
        **public,
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
    work_kw = dict(_kw)
    cred_id = str(work_kw.pop("cred_id", "") or "")
    if cred_id:
        import airc_passed_cred as _pcred

        work_kw["passed_cred"] = _pcred.GLOBAL_PASSED_CREDS.take(cred_id)
        work_kw["passed_requested"] = True
    if "passed_cred" in work_kw:
        work_kw["passed_requested"] = True

    def _finish(data: dict[str, Any]) -> NetworkVerbResult:
        hosts = list(data.get("hosts") or [])
        failures = list(data.get("failures") or data.get("log") or [])
        res = NetworkVerbResult(
            bool(data.get("ok", True)),
            accepted,
            job_id=qid,
            hosts=hosts,
            failures=failures,
            identity={
                k: data[k] for k in (
                    "identity", "account", "identity_label", "credman_missing",
                ) if k in data
            },
        )
        if on_done is not None:
            on_done(res)
        return res

    def _safe() -> NetworkVerbResult:
        try:
            data = work(action=action, whatif=whatif, **work_kw)
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

    # Staged secrets stay in memory, never in isolated-worker request files.
    if _iso.is_packaged_work(work) and not work_kw.get("passed_requested"):

        def _from_child(data: Any) -> None:
            # FR #5665: worker_died / isolated-fault must populate failures[]
            # (top-level error alone used to deliver empty success exit=0).
            if not isinstance(data, dict):
                payload = {
                    "ok": False,
                    "hosts": [],
                    "failures": [
                        {"step": "worker", "error": "worker_died", "detail": "bad-payload"}
                    ],
                    "log": [
                        {"step": "worker", "error": "worker_died", "detail": "bad-payload"}
                    ],
                }
            else:
                payload = dict(data)
                import airc_isolated as _iso

                if _iso.is_worker_fault(payload) or (
                    payload.get("ok") is False
                    and payload.get("error")
                    and not payload.get("failures")
                    and not payload.get("log")
                    and not payload.get("hosts")
                ):
                    detail = str(
                        payload.get("detail") or payload.get("error") or "no-result"
                    )[:300]
                    fault = {
                        "step": "worker",
                        "error": "worker_died",
                        "detail": detail,
                    }
                    payload = {
                        "ok": False,
                        "hosts": list(payload.get("hosts") or []),
                        "failures": [fault],
                        "log": [fault],
                        "error": "worker_died",
                        "detail": detail,
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
    source = str(payload.get("identity") or "")
    suffix = ""
    if source in ("passed", "credman", "system"):
        account = str(payload.get("account") or "")
        account = re.sub(r"[\s\x00-\x1f\x7f]", "_", account)
        suffix = f" identity={source} account={account}"
    # FR #5665: non-zero DONE when failures[] (parity EXTENSION #5644 / LEGION #5655).
    exit_code = 0 if nfail == 0 else 1
    summary = (
        f"NETWORK log hosts={nhost} failures={nfail} "
        f"action={payload.get('action')} bytes={len(raw)}{suffix}"
    )
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(payload.get("failures") or [], start=2):
        lines.append(
            f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}"
        )
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload_bounded
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(
                jid, exit_code, nbytes=len(raw), sha256=digest, via="dcc"
            ) + suffix
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
            done = f"DONE id={jid} exit={exit_code} via=irc reason=dcc-fail{suffix}"
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
    done = f"DONE id={jid} exit={exit_code} via=irc{suffix}"
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
