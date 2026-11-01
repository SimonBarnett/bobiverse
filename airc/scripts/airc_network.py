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
NETWORK_USAGE = "[diag] [-WhatIf]"


@dataclass
class NetworkVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    hosts: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    # FR #5711: safe identity metadata for log/DONE (never password).
    identity: str = ""
    identity_label: str = ""
    account: str = ""
    computer_account: str = ""
    credman_missing: bool = False
    credman_error: str = ""
    credman_target: str = ""

    def reply_text(self) -> str:
        return self.reply

    def identity_public(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.identity:
            out["identity"] = self.identity
        if self.identity_label:
            out["identity_label"] = self.identity_label
        if self.account:
            out["account"] = self.account
        if self.computer_account:
            out["computer_account"] = self.computer_account
        if self.credman_target:
            out["credman_target"] = self.credman_target
        if self.credman_missing:
            out["credman_missing"] = True
        if self.credman_error:
            out["credman_error"] = self.credman_error
        return out


def parse_network_command(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    m = _NETWORK_CMD_RE.match(raw)
    if not m:
        return None
    # FR #5711 / #5659: never accept plaintext password on IRC.
    try:
        import airc_identity as _ident

        if _ident.irc_line_has_plaintext_secret(raw):
            return {
                "qid": (m.group(1) or "").lower(),
                "error": "secrets-on-irc",
            }
    except Exception:
        pass
    qid = (m.group(1) or "").lower()
    tokens = [(t or "").strip() for t in (m.group(2) or "").split() if t.strip()]
    whatif = False
    cred_id = ""
    extra = False
    unknown = ""
    for tok in tokens:
        low = tok.lower()
        if low == "diag":
            continue
        if low == "-whatif":
            whatif = True
            continue
        if low.startswith("cred=") and re.fullmatch(r"cred=[0-9a-f]{8}", low):
            cred_id = low.split("=", 1)[1]
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


class NetworkAuthError(Exception):
    """FR #5711: ADSI bind failed with explicit credentials (no SYSTEM fallback)."""


_AUTH_MARKER = "NETWORK_AUTH_FAILED"
_AUTH_EXIT = 52


def _parse_ldap_nd_lines(stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cur_name = ""
    cur_dn = ""
    for line in (stdout or "").splitlines():
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


def default_ldap_enum(
    username: str | None = None,
    password: str | None = None,
) -> list[Any]:
    """AD computers via LDAP/ADSI (hostname + distinguishedName).

    FR #5521: NETWORK diag must not stub ``[]`` on a domain-joined console.
    Empty when not Windows, PowerShell missing, or DC/ADSI unavailable
    (workgroup / no-DC path — never invent hosts).

    FR #5711: optional ``username``/``password`` bind via PowerShell stdin
    (never argv / env). Auth failure raises ``NetworkAuthError``.
    """
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return []
    user = (username or "").strip()
    secret = password if password is not None else ""
    use_cred = bool(user and secret)
    if use_cred:
        # Credentialed DirectoryEntry bind; password only on stdin.
        script = (
            "$ErrorActionPreference='Stop';"
            "$user=[Console]::In.ReadLine();"
            "$pass=[Console]::In.ReadLine();"
            "try {"
            "$root=New-Object System.DirectoryServices.DirectoryEntry('LDAP://RootDSE',$user,$pass);"
            "$nc=[string]$root.Properties['defaultNamingContext'][0];"
            "$entry=New-Object System.DirectoryServices.DirectoryEntry(('LDAP://'+$nc),$user,$pass);"
            "$s=New-Object System.DirectoryServices.DirectorySearcher($entry);"
            "$s.Filter='(objectCategory=computer)';"
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
            "} catch {"
            "$msg=[string]$_.Exception.Message;"
            "if($msg -match '0x8007052E|0x80070005|logon failure|access is denied|access denied|bad username|unknown user'){"
            f"Write-Output '{_AUTH_MARKER}'; exit {_AUTH_EXIT}"
            "}"
            "throw"
            "}"
        )
        stdin_blob = user + "\n" + secret + "\n"
    else:
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
        stdin_blob = None
    try:
        p = subprocess.run(
            [ps, "-NoProfile", "-Command", script],
            input=stdin_blob,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return []
    out = p.stdout or ""
    if use_cred and (
        p.returncode == _AUTH_EXIT or _AUTH_MARKER in out
    ):
        raise NetworkAuthError("ldap-auth-failed")
    if p.returncode != 0:
        return []
    return _parse_ldap_nd_lines(out)


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
    ldap_enum: Callable[..., list[Any]] | None = None,
    resolve_ips: Callable[[str], list[str]] | None = None,
    extra_hosts: list[str] | None = None,
    passed: dict[str, str] | None = None,
    passed_requested: bool = False,
    credman_reader: Callable[[str], dict[str, str]] | None = None,
    system_fn: Callable[[], dict[str, str]] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5299 / #5711: hostname + ips[] + ou with identity (passed->CredMan->SYSTEM).

    Never uses extra_hosts. CredMan resolves inside the worker (isolated child).
    """
    _ = extra_hosts
    import airc_identity as _ident

    # Accept LEGION-style aliases from parent thread path.
    if passed is None and isinstance(_kw.get("passed_cred"), dict):
        passed = _kw.get("passed_cred")  # type: ignore[assignment]
    if not passed_requested and _kw.get("passed_requested"):
        passed_requested = True

    if passed_requested and not (
        passed
        and str(passed.get("username") or "").strip()
        and str(passed.get("password") or "")
    ):
        pub = {
            "identity": "passed",
            "identity_label": "passed (missing)",
            "account": "",
        }
        return {
            "ok": False,
            "action": action,
            "whatif": bool(whatif),
            "hosts": [],
            "log": [{"stage": "ldap", "error": "auth_failed", "reason": "cred-missing"}],
            "failures": [
                {"stage": "ldap", "error": "auth_failed", "reason": "cred-missing"}
            ],
            "error": "auth_failed",
            "ldap": False,
            **pub,
        }

    def _reader(tgt: str) -> dict[str, str]:
        if credman_reader is not None:
            # Tests inject zero-arg readers; accept both shapes.
            try:
                return credman_reader(tgt) or {}
            except TypeError:
                return credman_reader() or {}  # type: ignore[call-arg]
        return _ident.default_credman_reader(tgt)

    resolved = _ident.resolve_remote_identity(
        verb="network",
        passed=passed if isinstance(passed, dict) else None,
        passed_requested=False,
        credman_reader=_reader,
        system_fn=system_fn,
    )
    try:
        from airc_console_service import info as _info

        line = _ident.format_identity_fallback_log(verb="network", resolved=resolved)
        if line:
            _info(line)
    except Exception:
        pass
    pub = resolved.public_dict()
    if resolved.credman_missing:
        pub["credman_fell_through"] = "system"
    # computer_account is the SYSTEM account for the box (even when using CredMan).
    sys = (system_fn or _ident.system_computer_account)() or {}
    computer_account = str(sys.get("account") or sys.get("username") or "").strip()
    if computer_account:
        pub["computer_account"] = computer_account

    enum = ldap_enum or default_ldap_enum
    resolve = resolve_ips or default_resolve_ips
    use_secret = resolved.source in (
        _ident.IDENTITY_PASSED,
        _ident.IDENTITY_CREDMAN,
    )
    try:
        if use_secret:
            rows = list(
                enum(username=resolved.username, password=resolved.password) or []
            )
        else:
            rows = list(enum() or [])
    except NetworkAuthError:
        fail = {
            "stage": "ldap",
            "error": "auth_failed",
            "account": resolved.account,
            "identity": resolved.source,
        }
        return {
            "ok": False,
            "action": action,
            "whatif": bool(whatif),
            "hosts": [],
            "log": [fail],
            "failures": [fail],
            "error": "auth_failed",
            "ldap": False,
            **pub,
        }
    except TypeError:
        # Injected test fakes that take no kwargs: only legal for SYSTEM.
        if use_secret:
            fail = {
                "stage": "ldap",
                "error": "auth_failed",
                "detail": "ldap-enum-no-cred-support",
                "account": resolved.account,
                "identity": resolved.source,
            }
            return {
                "ok": False,
                "action": action,
                "whatif": bool(whatif),
                "hosts": [],
                "log": [fail],
                "failures": [fail],
                "error": "auth_failed",
                "ldap": False,
                **pub,
            }
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
        "failures": list(log),
        "ldap": ldap_ok,
        "limit": "" if ldap_ok else "workgroup-or-no-dc",
        **pub,
    }


def _identity_fields_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Copy safe identity keys from worker dict into NetworkVerbResult kwargs."""
    return {
        "identity": str(data.get("identity") or ""),
        "identity_label": str(data.get("identity_label") or ""),
        "account": str(data.get("account") or ""),
        "computer_account": str(data.get("computer_account") or ""),
        "credman_missing": bool(data.get("credman_missing")),
        "credman_error": str(data.get("credman_error") or ""),
        "credman_target": str(data.get("credman_target") or ""),
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

    # FR #5711: take DCC-staged cred in parent (isolated child has no shared stash).
    work_kw: dict[str, Any] = {}
    for k in ("credman_reader", "system_fn", "ldap_enum", "resolve_ips"):
        if k in _kw:
            work_kw[k] = _kw[k]
    cred_id = str(_kw.get("cred_id") or "").strip().lower()
    if cred_id:
        work_kw["cred_id"] = cred_id
        if "passed_cred" not in _kw and "passed" not in _kw:
            try:
                import airc_passed_cred as _pcred

                taken = _pcred.GLOBAL_PASSED_CREDS.take(cred_id)
                if taken:
                    work_kw["passed"] = taken
                work_kw["passed_requested"] = True
            except Exception:
                work_kw["passed_requested"] = True
    if "passed_cred" in _kw:
        work_kw["passed"] = _kw["passed_cred"]
        work_kw["passed_requested"] = True
    if "passed" in _kw:
        work_kw["passed"] = _kw["passed"]
        work_kw["passed_requested"] = True
    if _kw.get("passed_requested"):
        work_kw["passed_requested"] = True
    force_thread = bool(work_kw.get("passed") or work_kw.get("passed_requested"))

    def _finish(data: dict[str, Any]) -> NetworkVerbResult:
        hosts = list(data.get("hosts") or [])
        failures = list(data.get("failures") or data.get("log") or [])
        ident_kw = _identity_fields_from_data(data if isinstance(data, dict) else {})
        res = NetworkVerbResult(
            bool(data.get("ok", True)),
            accepted,
            job_id=qid,
            hosts=hosts,
            failures=failures,
            **ident_kw,
        )
        if on_done is not None:
            on_done(res)
        return res

    def _call_work() -> dict[str, Any]:
        data = work(action=action, whatif=whatif, **work_kw)
        return data if isinstance(data, dict) else {"ok": True, "hosts": [], "log": []}

    def _safe() -> NetworkVerbResult:
        try:
            data = _call_work()
        except Exception as exc:
            data = {
                "ok": False,
                "hosts": [],
                "log": [{"error": type(exc).__name__, "step": "worker"}],
                "failures": [{"error": type(exc).__name__, "step": "worker"}],
            }
        return _finish(data)

    if wait:
        return _safe()
    import airc_isolated as _iso

    if _iso.is_packaged_work(work):

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

        if force_thread:
            # Passed secrets must not cross packaged IPC; stay in-process.
            threading.Thread(target=_safe, name="airc-network-worker", daemon=True).start()
        else:
            # Isolated child resolves CredMan itself; never put secrets in the spec.
            _iso.start_isolated(
                wait=False,
                run=_call_work,
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
    # FR #5665: non-zero DONE when failures[] (parity EXTENSION #5644 / LEGION #5655).
    exit_code = 0 if nfail == 0 else 1
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
        sender = send_fn or _dcc.send_offer_payload_bounded
        try:
            sender(raw, offer)
            import airc_identity as _ident

            suf = _ident.done_identity_suffix(payload)
            done = _dcc.format_done_via_dcc(
                jid, exit_code, nbytes=len(raw), sha256=digest, via="dcc"
            ) + suf
            return {
                "via": "dcc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": [lines[0], done],
                "done": done,
            }
        except Exception as exc:
            import airc_identity as _ident

            suf = _ident.done_identity_suffix(payload)
            lines.append(
                f"err id={jid} seq={len(lines)+1} dcc failed: {exc}; falling back to IRC"
            )
            lines.append("CONT id=" + jid + " offset=1")
            done = f"DONE id={jid} exit={exit_code} via=irc reason=dcc-fail{suf}"
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
    import airc_identity as _ident

    suf = _ident.done_identity_suffix(payload)
    lines.append("CONT id=" + jid + " offset=1")
    done = f"DONE id={jid} exit={exit_code} via=irc{suf}"
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
