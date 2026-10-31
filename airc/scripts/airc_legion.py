"""Airc LEGION verb + isolated worker (FR #5308 / #5309).

FR-A: verb + stub. FR-B: import ``airc_network_installer`` for one host,
profile client, latest Release MSI, no --force. Auth matches UPDATE.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from socket import gethostname as socket_hostname
from typing import Any, Callable

# In-service module (FR #3991). LEGION must not shell a peer installer exe.
import airc_network_installer as _netinst  # noqa: F401

LEGION_TIMEOUT_S = 900

_LEGION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?LEGION(?:\s+(?P<rest>.*))?$"
)
_HOST_RE = re.compile(r"(?i)^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9\-]{1,63})*$")
_IPV4_RE = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}$"
)


@dataclass
class LegionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    status: str = ""
    error: str = ""
    failures: list[dict[str, Any]] = field(default_factory=list)

    def reply_text(self) -> str:
        return self.reply


def _classify_target(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return "empty"
    if "," in t or ";" in t:
        low = t.lower()
        if low.startswith("ou=") or "ou=" in low or low.startswith("cn="):
            return "ou"
        return "list"
    if t.lower().startswith("ou=") or t.lower().startswith("cn="):
        return "ou"
    if _IPV4_RE.match(t) or _HOST_RE.match(t):
        return None
    return "list"


def parse_legion_command(text: str) -> dict[str, Any] | None:
    m = _LEGION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group("rest") or "").strip()
    whatif = bool(re.search(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", rest))
    rest = re.sub(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", " ", rest).strip()
    parts = [p for p in rest.split() if p]
    qid = (m.group(1) or "").lower()
    if not parts:
        return {"qid": qid, "error": "empty", "target": "", "whatif": whatif}
    if len(parts) > 1:
        return {"qid": qid, "error": "list", "target": rest, "whatif": whatif}
    err = _classify_target(parts[0])
    if err:
        return {"qid": qid, "error": err, "target": parts[0], "whatif": whatif}
    return {"qid": qid, "error": None, "target": parts[0], "whatif": whatif}


_ALLOWED_MSI_PREFIX = "https://github.com/SimonBarnett/bobiverse/releases"
CREDMAN_TARGET = "PriorityAirc/LegionAdmin"
_CREDMAN_TARGET = CREDMAN_TARGET


class LegionCredmanError(RuntimeError):
    """CredMan target missing or unreadable (fail closed)."""


def stub_legion_work(
    target: str,
    *,
    whatif: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "target": target,
        "whatif": bool(whatif),
        "invoked_installer": False,
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
    }


def _msi_allowed(msi: str | None) -> bool:
    raw = (msi or "").strip()
    if not raw:
        return True
    if "://" not in raw:
        return True
    return raw.lower().startswith(_ALLOWED_MSI_PREFIX.lower())


def read_legion_credman(
    *,
    target: str = CREDMAN_TARGET,
    reader: Callable[[], dict[str, str]] | None = None,
) -> dict[str, str]:
    """Read ``PriorityAirc/LegionAdmin``. Never log the secret. Fail closed."""
    if reader is not None:
        got = reader() or {}
        user = str(got.get("username") or "").strip()
        pw = str(got.get("password") or "")
        if not user or not pw:
            raise LegionCredmanError("credman-missing")
        return {"username": user, "password": pw}
    import subprocess

    ps = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32\WindowsPowerShell\v1.0\powershell.exe"
    script = r"""
param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LegionCredRead {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct CREDENTIAL {
    public uint Flags; public uint Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public uint CredentialBlobSize; public IntPtr CredentialBlob; public uint Persist;
    public uint AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool CredRead(string target, uint type, int reserved, out IntPtr cred);
  [DllImport("advapi32.dll", SetLastError=true)]
  public static extern void CredFree(IntPtr cred);
  public static string ReadPair(string target) {
    IntPtr p;
    if (!CredRead(target, 1, 0, out p) || p == IntPtr.Zero) return null;
    try {
      var c = (CREDENTIAL)Marshal.PtrToStructure(p, typeof(CREDENTIAL));
      string user = c.UserName ?? "";
      string pw = "";
      if (c.CredentialBlob != IntPtr.Zero && c.CredentialBlobSize > 0)
        pw = Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2) ?? "";
      return "U=" + user + "\nP=" + pw;
    } finally { CredFree(p); }
  }
}
"@
$pair = [LegionCredRead]::ReadPair($Target)
if ($null -eq $pair) { Write-Output 'CRED_MISSING'; exit 2 }
[Console]::Out.Write($pair)
"""
    try:
        p = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, "-Target", target],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        raise LegionCredmanError(f"credman-read-failed:{type(exc).__name__}") from exc
    out = p.stdout or ""
    if p.returncode != 0 or out.strip() == "CRED_MISSING":
        raise LegionCredmanError("credman-missing")
    user, pw = "", ""
    for line in out.splitlines():
        if line.startswith("U="):
            user = line[2:].strip()
        elif line.startswith("P="):
            pw = line[2:]
    if not user or not pw:
        raise LegionCredmanError("credman-empty")
    return {"username": user, "password": pw}


def default_legion_credman() -> dict[str, str]:
    """Live CredMan ``PriorityAirc/LegionAdmin``. Empty dict means missing (fail closed)."""
    try:
        return read_legion_credman()
    except LegionCredmanError:
        return {}


def _candidate_version_from_msi_name(msi: Path) -> str:
    name = msi.stem
    if name.lower().startswith("airc-"):
        return name[5:]
    return name


def _resolve_legion_msi_path(spec: dict[str, Any]) -> Path:
    """Local path, allowed GitHub release URL, or Latest download (FR #5309 / #5382)."""
    from airc_network_installer.github_msi import download_latest_airc_msi
    from urllib.request import urlretrieve

    raw = (spec.get("msi") or "").strip()
    if not raw:
        dest = Path(str(spec.get("download_dir") or os.getcwd()))
        dest.mkdir(parents=True, exist_ok=True)
        msi_path, _tag = download_latest_airc_msi(dest)
        return msi_path
    if "://" in raw:
        if not _msi_allowed(raw):
            raise ValueError("foreign-msi-url")
        dest = Path(str(spec.get("download_dir") or os.getcwd()))
        dest.mkdir(parents=True, exist_ok=True)
        name = raw.rstrip("/").split("/")[-1] or "airc-download.msi"
        if not name.lower().endswith(".msi"):
            name = "airc-download.msi"
        out = dest / name
        urlretrieve(raw, out)  # noqa: S310 — allowlist-checked bobiverse release URL only
        return out
    return Path(raw)


def default_installer_run(spec: dict[str, Any]) -> dict[str, Any]:
    """Import-path invoke. WhatIf / dry_run never calls install_remote (FR #5382)."""
    from airc_network_installer.install import find_psexec, install_local, install_remote

    host = str((spec.get("hosts") or [""])[0] or "")
    dry = bool(spec.get("dry_run"))
    profile = str(spec.get("profile") or "client")
    force = bool(spec.get("force"))
    timeout_s = float(spec.get("timeout_s") or LEGION_TIMEOUT_S)
    if dry:
        return {
            "ok": True,
            "status": "dry-run",
            "host": host,
            "profile": profile,
            "force": force,
            "timeout_s": timeout_s,
        }

    try:
        msi_path = _resolve_legion_msi_path(spec)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": f"msi-resolve:{type(exc).__name__}",
        }
    if not msi_path.is_file():
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": "msi-missing",
        }

    password = os.environ.get("AIRC_LEGION_PASSWORD", "")
    user = str(spec.get("username") or "")
    log_dir = Path(str(spec.get("log_dir") or "airc-install-logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    psexec = find_psexec(str(spec.get("psexec") or ""))
    if not psexec:
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": "psexec-missing",
            "msi": str(msi_path),
            "log_dir": str(log_dir),
        }

    candidate = _candidate_version_from_msi_name(msi_path)
    local_names = {socket_hostname().lower(), "localhost", "127.0.0.1"}
    try:
        if host.lower() in local_names:
            row = install_local(
                msi_path=msi_path,
                candidate_version=candidate,
                profile=profile,
                force=force,
                log_dir=log_dir,
                dry_run=False,
            )
        else:
            row = install_remote(
                host=host,
                msi_path=msi_path,
                candidate_version=candidate,
                profile=profile,
                force=force,
                psexec=psexec,
                username=user,
                password=password,
                log_dir=log_dir,
                dry_run=False,
                timeout_s=timeout_s,
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "host": host,
            "error": f"install:{type(exc).__name__}",
            "msi": str(msi_path),
            "log_dir": str(log_dir),
        }

    status = str(getattr(row, "status", "") or "failed")
    ok = status in ("success", "reboot_required", "skipped", "dry-run")
    return {
        "ok": ok,
        "status": status,
        "host": host,
        "msi": str(msi_path),
        "action": getattr(row, "action", ""),
        "previous_version": getattr(row, "previous_version", ""),
        "detail": getattr(row, "detail", ""),
        "log_path": getattr(row, "log_path", ""),
        "username": user,
        "has_password": bool(password),
        "log_dir": str(log_dir),
        "profile": profile,
        "force": force,
        "timeout_s": timeout_s,
    }


def installer_legion_work(
    target: str,
    *,
    whatif: bool = False,
    run_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    credman: Callable[[], dict[str, str]] | None = None,
    msi: str | None = None,
    log_dir: str | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5309: one host, client profile, latest Release MSI, no --force."""
    if not _msi_allowed(msi):
        return {
            "ok": False,
            "target": target,
            "whatif": bool(whatif),
            "invoked_installer": False,
            "force": False,
            "timeout_s": LEGION_TIMEOUT_S,
            "profile": "client",
            "error": "foreign-msi-url",
        }
    ident = (credman or default_legion_credman)() or {}
    user = str(ident.get("username") or "").strip()
    secret = str(ident.get("password") or "")
    if not user or not secret:
        return {
            "ok": False,
            "target": target,
            "whatif": bool(whatif),
            "invoked_installer": False,
            "force": False,
            "timeout_s": LEGION_TIMEOUT_S,
            "profile": "client",
            "error": "credman-missing",
        }
    spec: dict[str, Any] = {
        "hosts": [target],
        "profile": "client",
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "dry_run": bool(whatif),
        "whatif": bool(whatif),
        "msi": (msi or "").strip(),
        "log_dir": log_dir or "airc-install-logs",
        "credman_target": _CREDMAN_TARGET,
    }
    if user:
        spec["username"] = user
        spec["password_via"] = "secure-env"
        if secret:
            os.environ["AIRC_LEGION_PASSWORD"] = secret
    try:
        out = (run_fn or default_installer_run)(spec)
    finally:
        if secret:
            os.environ.pop("AIRC_LEGION_PASSWORD", None)
    status = str((out or {}).get("status") or "")
    return {
        "ok": bool((out or {}).get("ok", True)),
        "target": target,
        "whatif": bool(whatif),
        "dry_run": bool(whatif),
        "invoked_installer": True,
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
        "hosts": [target],
        "status": status,
        "log_dir": spec["log_dir"],
        "error": (out or {}).get("error"),
    }


def run_legion_verb(
    *,
    target: str = "",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    on_done: Callable[[LegionVerbResult], Any] | None = None,
    **_kw: Any,
) -> LegionVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or installer_legion_work
    extra = " whatif=1" if whatif else ""
    accepted = (
        f"LEGION accepted id={qid} target={target} timeout={LEGION_TIMEOUT_S}{extra}\n"
        f"DONE id={qid} exit=0"
    )
    work_kw: dict[str, Any] = {}
    if "credman" in _kw:
        work_kw["credman"] = _kw["credman"]

    def _finish(data: dict[str, Any], *, reply: str | None = None) -> LegionVerbResult:
        err = str(data.get("error") or "")
        fails = list(data.get("failures") or [])
        if not fails and err:
            fails = [{"host": data.get("target") or target, "error": err}]
        res = LegionVerbResult(
            bool(data.get("ok", True)),
            reply or accepted,
            job_id=qid,
            status=str(data.get("status") or ""),
            error=err,
            failures=fails,
        )
        if on_done is not None:
            on_done(res)
        return res

    def _call_work() -> dict[str, Any]:
        try:
            data = work(target, whatif=whatif, **work_kw)
        except TypeError:
            data = work(target=target, whatif=whatif, **work_kw)
        return data if isinstance(data, dict) else {}

    def _safe() -> LegionVerbResult:
        try:
            data = _call_work()
            if str(data.get("error") or "") == "credman-missing":
                return _finish(
                    data,
                    reply=f"DONE id={qid} exit=126 credman-missing",
                )
            return _finish(data)
        except Exception as exc:
            return _finish(
                {
                    "ok": False,
                    "target": target,
                    "error": type(exc).__name__,
                    "status": "",
                }
            )

    if wait:
        # FR #5389: CredRead lives here (or in installer_legion_work), not on accept.
        return _safe()
    threading.Thread(target=_safe, name="airc-legion-worker", daemon=True).start()
    return LegionVerbResult(True, accepted, job_id=qid)


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


def build_legion_log(
    *,
    target: str = "",
    whatif: bool = False,
    summary: str = "",
    failures: list[dict] | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    """FR #5311: installer log + failures[]; secrets stripped."""
    log: dict[str, Any] = {
        "target": target,
        "whatif": bool(whatif),
        "summary": summary,
        "failures": list(failures or []),
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
        "force": False,
    }
    if extra:
        for k, v in extra.items():
            if not _SECRET_KEY_RE.search(str(k)):
                log[k] = v
    log = _scrub(log)
    log["failure_count"] = len(log.get("failures") or [])
    return log


def legion_log_bytes(log: dict[str, Any]) -> bytes:
    return (json.dumps(log, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def deliver_legion_log(
    *,
    job_id: str,
    log: dict[str, Any],
    offer: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    import airc_dcc_bulk as _dcc

    jid = (job_id or "").strip().lower() or "00000000"
    raw = legion_log_bytes(log)
    digest = hashlib.sha256(raw).hexdigest()
    nfail = int(log.get("failure_count") or 0)
    summary = (
        f"LEGION log target={log.get('target')} failures={nfail} "
        f"bytes={len(raw)}"
    )
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(log.get("failures") or [], start=2):
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
            done = f"DONE id={jid} exit=0 via=irc reason=dcc-fail"
            lines.append(done)
            return {
                "via": "irc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": lines,
                "done": done,
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
    }
