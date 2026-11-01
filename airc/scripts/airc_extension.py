"""Airc EXTENSION verb + isolated worker (FR #5290 / #5291 / #5292 / #5293 / #5520).

FR-A: verb + isolated worker. FR-B: DC + GPO Priority-web-extension.
FR-C: LDAP enum + per-host Chrome/Edge ForceInstall fallback (always after GPO).
FR #5364: machine account first; CredMan PriorityAirc/ExtensionAdmin on access-denied.
FR-D: structured log via DCCLISTEN or IRC CONT.
FR #5520: DCC log joins worker via on_done (do not build from accept defaults).
Auth matches UPDATE. Never secrets on IRC.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFAULT_EXTENSION_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"
CHROME_WEB_STORE_UPDATE = "https://clients2.google.com/service/update2/crx"
DEFAULT_UPDATE_URL = CHROME_WEB_STORE_UPDATE
DEFAULT_GPO_NAME = "Priority-web-extension"
FORCE_INSTALL_ENTRY = f"{DEFAULT_EXTENSION_ID};{DEFAULT_UPDATE_URL}"
CHROME_FORCE_KEY = r"SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist"
EDGE_FORCE_KEY = r"SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist"
CREDMAN_TARGET = "PriorityAirc/ExtensionAdmin"
GPO_SCRIPT_NAME = "Invoke-AircExtensionGpo.ps1"

_EXTENSION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?EXTENSION(?:\s+(?P<rest>.*))?$"
)
EXTENSION_USAGE = "install|status [-WhatIf]"


@dataclass
class ExtensionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    payload: dict[str, Any] | None = None

    def reply_text(self) -> str:
        return self.reply


def parse_extension_command(text: str) -> dict[str, Any] | None:
    m = _EXTENSION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    import airc_identity as _ident
    import airc_passed_cred as _pcred

    qid = (m.group(1) or "").lower()
    if _ident.irc_line_has_plaintext_secret(text or ""):
        return {"qid": qid, "usage": True, "error": "secrets-on-irc"}
    rest = (m.group("rest") or "").strip()
    cred_id, rest = _pcred.extract_cred_ref(rest)
    parts = [(p or "").strip() for p in rest.split() if p.strip()]
    if not parts or parts[0].lower() not in {"install", "status"}:
        return {"qid": qid, "usage": True, "cred_id": cred_id}
    action = parts[0].lower()
    whatif = False
    unknown = ""
    extra = False
    for tok in parts[1:]:
        if tok.lower() == "-whatif":
            whatif = True
            continue
        if tok.startswith("-"):
            unknown = tok
            break
        extra = True
    if unknown:
        return {"qid": qid, "usage": True, "unknown_flag": unknown, "cred_id": cred_id}
    if extra:
        return {"qid": qid, "usage": True, "cred_id": cred_id}
    return {
        "qid": qid,
        "action": action,
        "whatif": whatif,
        "cred_id": cred_id,
    }




def _is_frozen_airc_runtime() -> bool:
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def gpo_script_candidates() -> list[Path]:
    """Ordered search paths for Invoke-AircExtensionGpo.ps1 (FR #5522)."""
    name = GPO_SCRIPT_NAME
    out: list[Path] = []
    mei = getattr(sys, "_MEIPASS", None)
    frozen = _is_frozen_airc_runtime()
    # Frozen one-file: bundled --add-data lands under _MEIPASS (must win).
    if mei:
        out.append(Path(mei) / name)
        out.append(Path(mei) / "scripts" / name)
    if frozen:
        roots: list[Path] = []
        env = (os.environ.get("AIRC_INSTALL_ROOT") or "").strip()
        if env:
            roots.append(Path(env))
        exe = Path(sys.executable).resolve()
        # Pack stages airc\airc.exe under the install root.
        if exe.parent.name.lower() == "airc":
            roots.append(exe.parent.parent)
            roots.append(exe.parent)
        else:
            roots.append(exe.parent)
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve()) if root.exists() else str(root)
            if key in seen:
                continue
            seen.add(key)
            # Flat install: <root>\scripts\...
            out.append(root / "scripts" / name)
            # Nested: <root>\airc\scripts\... (seen on MarchHare hotpatch trees)
            out.append(root / "airc" / "scripts" / name)
            out.append(root / name)
    # Dev / non-frozen: module directory (and still a fallback when frozen).
    out.append(Path(__file__).resolve().parent / name)
    return out


def gpo_script_path() -> Path:
    """Resolve GPO helper for source, install tree, or frozen airc.exe (FR #5522)."""
    cands = gpo_script_candidates()
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return cands[0]


def run_extension_gpo_work(
    action: str = "install",
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
    update_url: str = DEFAULT_UPDATE_URL,
    gpo_name: str = DEFAULT_GPO_NAME,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """FR #5291: DC discovery + GPO ForceInstall for Chrome and Edge."""
    eid = (extension_id or DEFAULT_EXTENSION_ID).strip() or DEFAULT_EXTENSION_ID
    url = (update_url or DEFAULT_UPDATE_URL).strip() or DEFAULT_UPDATE_URL
    name = (gpo_name or DEFAULT_GPO_NAME).strip() or DEFAULT_GPO_NAME
    if runner is not None:
        body = runner(
            action=action,
            whatif=whatif,
            extension_id=eid,
            update_url=url,
            gpo_name=name,
        )
        if not isinstance(body, dict):
            return {
                "ok": False,
                "gpo": "fail",
                "reason": "bad_runner",
                "wrote_gpo": False,
                "wrote_registry": False,
                "extension_id": eid,
                "browsers": [],
                "policy_names": [],
            }
        body.setdefault("extension_id", eid)
        body.setdefault("wrote_registry", False)
        body.setdefault("browsers", ["chrome", "edge"] if body.get("ok") else [])
        body.setdefault(
            "policy_names",
            [name] if body.get("gpo") in {"ok", "present"} else [],
        )
        return body
    script = gpo_script_path()
    if not script.is_file():
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_script_missing",
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    args = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Action",
        action,
        "-ExtensionId",
        eid,
        "-UpdateUrl",
        url,
        "-GpoName",
        name,
    ]
    if whatif:
        args.append("-WhatIf")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_invoke_failed",
            "error": type(exc).__name__,
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    raw_lines = (proc.stdout or "").strip().splitlines()
    blob = raw_lines[-1] if raw_lines else ""
    try:
        data = json.loads(blob) if blob else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict) or not data:
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_bad_json" if blob else "gpo_empty_output",
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-400:],
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    data.setdefault("wrote_registry", False)
    data.setdefault("extension_id", eid)
    return data


def extension_gpo_then_fill_holes(
    action: str = "install",
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
    **kw: Any,
) -> dict[str, Any]:
    """Vision order: GPO first, then always FR-C fill-holes."""
    gpo_kw = {k: kw[k] for k in ("update_url", "gpo_name", "runner") if k in kw}
    hole_kw = {k: v for k, v in kw.items() if k not in {"update_url", "gpo_name", "runner"}}
    gpo = run_extension_gpo_work(
        action, whatif=whatif, extension_id=extension_id, **gpo_kw
    )
    holes = fill_holes_work(
        action, whatif=whatif, extension_id=extension_id, **hole_kw
    )
    out = dict(holes) if isinstance(holes, dict) else {"ok": False, "reason": "bad_fill_holes"}
    out["gpo"] = gpo.get("gpo") if isinstance(gpo, dict) else "fail"
    out["gpo_detail"] = gpo
    out["wrote_gpo"] = bool(isinstance(gpo, dict) and gpo.get("wrote_gpo"))
    if isinstance(gpo, dict):
        out["browsers"] = list(
            dict.fromkeys(list(gpo.get("browsers") or []) + list(out.get("browsers") or []))
        )
        out["policy_names"] = list(gpo.get("policy_names") or [])
        out["gpo_reason"] = gpo.get("reason")
    out["ok"] = bool(isinstance(gpo, dict) and gpo.get("ok")) or bool(out.get("ok"))
    return out


def service_extension_runner(**kw: Any) -> ExtensionVerbResult:
    """Production: GPO then fill-holes, isolated (FR #5291 / parent S4).

    Do not wait on the handler --- that blocks IRC receive for nltest/GPO.
    Structured gpo=ok/fail belongs on the DCC/CONT log (FR #5293), not the accept line.
    """
    return run_extension_verb(worker=extension_gpo_then_fill_holes, wait=False, **kw)

def stub_extension_work(
    action: str,
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
) -> dict[str, Any]:
    """FR-A stub: never writes GPO/registry (FR-B)."""
    return {
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "wrote_gpo": False,
        "wrote_registry": False,
        "extension_id": extension_id,
    }


def forcelist_value_has_extension(value: str, extension_id: str) -> bool:
    """FR #5660: present only when the forcelist entry id (before ';') equals extension_id."""
    ext = (extension_id or "").strip().lower()
    if not ext:
        return False
    first = str(value or "").split(";", 1)[0].strip().lower()
    return first == ext


def next_forcelist_name(
    existing_names: list[str],
    existing_values: list[str],
    extension_id: str,
) -> str | None:
    """FR #5538: next unused 1,2,3... or None if the extension id is already present.

    FR #5660: match the id before ';' (not a substring anywhere in the value).
    """
    ext = (extension_id or "").strip()
    if ext and any(forcelist_value_has_extension(v, ext) for v in existing_values):
        return None
    used = {str(n) for n in existing_names}
    n = 1
    while str(n) in used:
        n += 1
    return str(n)


def registry_values_look_like_windows(values: dict[str, Any]) -> bool:
    """FR #5660: Samba winreg often fakes only SystemRoot + CurrentVersion=6.1.

    Real Windows exposes ProductName and/or CurrentBuild(Number).
    """
    product = str(values.get("ProductName") or "").strip()
    if product:
        return True
    build = str(
        values.get("CurrentBuild") or values.get("CurrentBuildNumber") or ""
    ).strip()
    return bool(build)


def default_is_windows_host(host: str) -> bool:
    """FR #5660: True unless remote registry is reachable and looks like Samba.

    Unreachable hosts return True so fill-holes can still probe / report
    unreachable-registry via the existing forcelist path (unit tests use
    fake hostnames). Samba winreg that answers CurrentVersion without
    ProductName/CurrentBuild returns False -> ``skipped: not_windows``.
    """
    import winreg

    name = (host or "").strip()
    if not name:
        return True
    try:
        rem = winreg.ConnectRegistry(name, winreg.HKEY_LOCAL_MACHINE)
    except OSError:
        return True
    try:
        try:
            key = winreg.OpenKey(
                rem, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            )
        except OSError:
            # Connected but no CurrentVersion — treat as non-Windows.
            return False
        try:
            found: dict[str, Any] = {}
            idx = 0
            while idx < 64:
                try:
                    n, v, _typ = winreg.EnumValue(key, idx)
                except OSError:
                    break
                found[str(n)] = v
                idx += 1
            return registry_values_look_like_windows(found)
        finally:
            winreg.CloseKey(key)
    finally:
        winreg.CloseKey(rem)


def default_dc_hostnames() -> list[str]:
    """ADSI Domain Controllers (SERVER_TRUST_ACCOUNT). Empty when ADSI unavailable.

    FR #5538: live fill-holes must skip DCs; tests may still inject ``is_dc`` /
    ``dc_enum`` without calling this.
    """
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return []
    # 8192 = ADS_UF_SERVER_TRUST_ACCOUNT (domain controller).
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=[adsisearcher]"
        "'(&(objectCategory=computer)(userAccountControl:1.2.840.113556.1.4.803:=8192))';"
        "$s.PageSize=200; [void]$s.PropertiesToLoad.Add('name');"
        "($s.FindAll() | ForEach-Object { $_.Properties['name'][0] })"
    )
    try:
        p = subprocess.run(
            [ps, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=12,
        )
    except Exception:
        return []
    if p.returncode != 0:
        return []
    return [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]


def force_install_value(extension_id: str = DEFAULT_EXTENSION_ID) -> str:
    return f"{extension_id};{CHROME_WEB_STORE_UPDATE}"


def default_ldap_enum() -> list[str]:
    """AD computer names via LDAP/ADSI. Empty when DC is unavailable (no invented hosts)."""
    import os
    import shutil
    import subprocess

    if os.name != "nt":
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return []
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=[adsisearcher]'(objectCategory=computer)';"
        "$s.PageSize=500; [void]$s.PropertiesToLoad.Add('name');"
        "($s.FindAll() | ForEach-Object { $_.Properties['name'][0] })"
    )
    try:
        p = subprocess.run(
            [ps, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=12,
        )
    except Exception:
        return []
    if p.returncode != 0:
        return []
    return [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]


def default_ping_host(host: str) -> bool:
    import os
    import shutil
    import subprocess

    ping = shutil.which("ping")
    if not ping or not (host or "").strip():
        return False
    args = (
        [ping, "-n", "1", "-w", "800", host]
        if os.name == "nt"
        else [ping, "-c", "1", "-W", "1", host]
    )
    try:
        p = subprocess.run(args, capture_output=True, timeout=3)
        return p.returncode == 0
    except Exception:
        return False


def tcp_port_open(host: str, port: int = 445, timeout_s: float = 1.5) -> bool:
    """True when TCP connect to host:port succeeds (SMB probe uses 445)."""
    import socket

    if not (host or "").strip():
        return False
    try:
        with socket.create_connection((host.strip(), int(port)), timeout=float(timeout_s)):
            return True
    except OSError:
        return False


def is_access_denied(exc: BaseException) -> bool:
    """True for remote-registry access-denied (FR #5364)."""
    if isinstance(exc, PermissionError):
        return True
    if int(getattr(exc, "winerror", 0) or 0) == 5:
        return True
    if int(getattr(exc, "errno", 0) or 0) in (5, 13):
        return True
    msg = str(exc).lower()
    return "access is denied" in msg or "access denied" in msg


def is_ipc_auth_failed(exc: BaseException) -> bool:
    """True for IPC$/CredMan logon failures (FR #5708).

    Win32: 5 access-denied, 86 bad password, 1326 logon failure, 1385 logon type.
    """
    if is_access_denied(exc):
        return True
    win = int(getattr(exc, "winerror", 0) or 0)
    err = int(getattr(exc, "errno", 0) or 0)
    return (win or err) in (86, 1326, 1385)


def wnet_add_ipc(host: str, username: str, password: str) -> str:
    """Connect ``\\\\host\\IPC$`` via WNetAddConnection2W (FR #5709).

    Password stays in process memory only — never on ``net use`` argv / 4688.
    Raises ``OSError`` with ``winerror`` set to the WNet status (never a blanket 5).
    Returns the remote UNC used (for cancel).
    """
    import ctypes
    from ctypes import wintypes

    class NETRESOURCEW(ctypes.Structure):
        _fields_ = [
            ("dwScope", wintypes.DWORD),
            ("dwType", wintypes.DWORD),
            ("dwDisplayType", wintypes.DWORD),
            ("dwUsage", wintypes.DWORD),
            ("lpLocalName", wintypes.LPWSTR),
            ("lpRemoteName", wintypes.LPWSTR),
            ("lpComment", wintypes.LPWSTR),
            ("lpProvider", wintypes.LPWSTR),
        ]

    remote = r"\\{0}\IPC$".format(host)
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    add = mpr.WNetAddConnection2W
    add.argtypes = [
        ctypes.POINTER(NETRESOURCEW),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    add.restype = wintypes.DWORD

    nr = NETRESOURCEW()
    nr.dwType = 0  # RESOURCETYPE_ANY
    nr.lpRemoteName = remote
    user_w = username if username else None
    pass_w = password if password else None
    rc = int(add(ctypes.byref(nr), pass_w, user_w, 0) or 0)
    if rc != 0:
        raise ctypes.WinError(rc)
    return remote


def wnet_cancel(remote: str) -> None:
    """Drop a WNet connection. Never raises secrets; ignore cancel failures."""
    import ctypes
    from ctypes import wintypes

    if not remote:
        return
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    cancel = mpr.WNetCancelConnection2W
    cancel.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL]
    cancel.restype = wintypes.DWORD
    cancel(remote, 0, True)


def classify_extension_host_error(
    exc: BaseException | None,
    *,
    icmp_ok: bool | None = None,
    smb_ok: bool | None = None,
) -> dict[str, Any]:
    """FR #5661: map fallback reach failures to operator-facing codes + detail.

    Codes: access_denied, remote_registry_stopped, smb_blocked, host_down,
    unreachable (only when nothing answers / unclassified silence).
    """
    detail = (str(exc) if exc is not None else "")[:300]
    if exc is not None and is_access_denied(exc):
        return {"error": "access_denied", "detail": detail or "access-denied"}
    msg = detail.lower()
    win = int(getattr(exc, "winerror", 0) or 0) if exc is not None else 0
    err_no = int(getattr(exc, "errno", 0) or 0) if exc is not None else 0
    code = win or err_no
    rpc_hints = code in (1722, 1723, 1726, 1727, 1753, 1747) or (
        "rpc server is unavailable" in msg
        or "rpc server unavailable" in msg
        or "endpoint mapper" in msg
        or ("remote procedure call" in msg and "fail" in msg)
        or ("rpc" in msg and "timeout" in msg)
    )
    if rpc_hints:
        return {
            "error": "remote_registry_stopped",
            "detail": detail or "rpc-unavailable",
        }
    smb_hints = code in (51, 53, 64, 65, 67, 1231, 121) or (
        "network path was not found" in msg
        or "network name cannot be found" in msg
        or "no network provider" in msg
        or "semaphore timeout" in msg
        or "timed out" in msg
    )
    if smb_ok is False and icmp_ok is False and not rpc_hints:
        return {"error": "host_down", "detail": detail or "no-icmp-no-smb"}
    if smb_ok is False or smb_hints:
        return {"error": "smb_blocked", "detail": detail or "smb-445-failed"}
    if icmp_ok is False and smb_ok is False:
        return {"error": "host_down", "detail": detail or "no-icmp-no-smb"}
    if exc is None and icmp_ok is False and smb_ok is None:
        return {"error": "unreachable", "detail": "icmp-failed"}
    if exc is None and icmp_ok is False:
        return {"error": "host_down", "detail": "icmp-failed"}
    return {"error": "unreachable", "detail": detail or "no-response"}


def default_extension_credman() -> dict[str, str]:
    """CredMan ``PriorityAirc/ExtensionAdmin``. Empty means missing (fail closed)."""
    try:
        from airc_legion import LegionCredmanError, read_legion_credman

        return read_legion_credman(target=CREDMAN_TARGET)
    except Exception:
        return {}


def default_apply_force_install_as(
    host: str,
    product: str,
    value: str,
    username: str,
    password: str,
) -> bool:
    """Retry registry write after IPC$ with CredMan user. Never log the secret.

    FR #5585: return the wrote bool from default_apply_force_install.
    FR #5709: WNetAddConnection2W so the password is never on process argv / 4688.
    FR #5708: surface the real WNet winerror (53/67 host path, 1326/5 auth) —
    never remap every failure to OSError(5) ``credman-ipc-failed``.
    """
    remote = r"\\{0}\IPC$".format(host)
    try:
        remote = wnet_add_ipc(host, username, password)
        return bool(default_apply_force_install(host, product, value))
    finally:
        with contextlib.suppress(Exception):
            wnet_cancel(remote)


def default_apply_force_install(host: str, product: str, value: str) -> bool:
    import winreg

    key_path = CHROME_FORCE_KEY if product == "chrome" else EDGE_FORCE_KEY
    rem = winreg.ConnectRegistry(host, winreg.HKEY_LOCAL_MACHINE)
    try:
        key = winreg.CreateKey(rem, key_path)
        try:
            names: list[str] = []
            values: list[str] = []
            idx = 0
            while True:
                try:
                    n, v, _typ = winreg.EnumValue(key, idx)
                except OSError:
                    break
                names.append(str(n))
                values.append(str(v or ""))
                idx += 1
            ext_id = (value or "").split(";", 1)[0]
            slot = next_forcelist_name(names, values, ext_id)
            if slot is None:
                return False
            winreg.SetValueEx(key, slot, 0, winreg.REG_SZ, value)
            return True
        finally:
            winreg.CloseKey(key)
    finally:
        winreg.CloseKey(rem)


def default_read_forcelist(host: str, product: str) -> tuple[list[str], list[str]]:
    """FR #5585: read Chrome/Edge ForceInstall values (no write)."""
    import winreg

    key_path = CHROME_FORCE_KEY if product == "chrome" else EDGE_FORCE_KEY
    rem = winreg.ConnectRegistry(host, winreg.HKEY_LOCAL_MACHINE)
    try:
        try:
            key = winreg.OpenKey(rem, key_path)
        except OSError:
            return [], []
        try:
            names: list[str] = []
            values: list[str] = []
            idx = 0
            while True:
                try:
                    n, v, _typ = winreg.EnumValue(key, idx)
                except OSError:
                    break
                names.append(str(n))
                values.append(str(v or ""))
                idx += 1
            return names, values
        finally:
            winreg.CloseKey(key)
    finally:
        winreg.CloseKey(rem)


def probe_host_forcelist(
    host: str,
    extension_id: str,
    *,
    reader: Callable[[str, str], tuple[list[str], list[str]]] | None = None,
) -> dict[str, Any]:
    """Return would_write/present per browser. Raises when the registry is unreadable.

    FR #5661: callers classify the raised error (do not swallow as None).
    """
    read = reader or default_read_forcelist
    cn, cv = read(host, "chrome")
    en, ev = read(host, "edge")
    chrome_need = next_forcelist_name(cn, cv, extension_id) is not None
    edge_need = next_forcelist_name(en, ev, extension_id) is not None
    return {
        "chrome_present": not chrome_need,
        "edge_present": not edge_need,
        "would_write": chrome_need or edge_need,
    }


def _apply_wrote(fn: Callable[..., Any], *args: Any) -> bool:
    """Void writers count as wrote; default_apply returns False on already-present."""
    out = fn(*args)
    if out is None:
        return True
    return bool(out)


def fill_holes_work(
    action: str,
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
    ldap_enum: Callable[[], list[str]] | None = None,
    ping_host: Callable[[str], bool] | None = None,
    apply_force_install: Callable[[str, str, str], None] | None = None,
    apply_force_install_as: Callable[..., None] | None = None,
    credman_reader: Callable[[], dict[str, str]] | None = None,
    extra_hosts: list[str] | None = None,
    is_dc: Callable[[str], bool] | None = None,
    dc_enum: Callable[[], list[str]] | None = None,
    read_forcelist: Callable[[str, str], tuple[list[str], list[str]]] | None = None,
    is_windows_host: Callable[[str], bool] | None = None,
    tcp_probe: Callable[..., bool] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5292: LDAP enum + per-host Chrome/Edge ForceInstall. Never uses extra_hosts.

    FR #5364: on access-denied, retry with CredMan PriorityAirc/ExtensionAdmin.
    FR #5538: status is read-only; skip DCs; append a free forcelist name.
    FR #5585: would_write / chrome/edge true only when a forcelist slot is free.
    FR #5660: skip non-Windows (Samba winreg) as ``not_windows`` --- never present.
    FR #5661: ICMP alone is not unreachable; classify smb_blocked /
    remote_registry_stopped / access_denied / host_down with detail text.
    FR #5659: privileged writes use passed -> CredMan -> SYSTEM identity.
    """
    _ = extra_hosts
    enum = ldap_enum or default_ldap_enum
    ping = ping_host or default_ping_host
    apply = apply_force_install or default_apply_force_install
    apply_as = apply_force_install_as or default_apply_force_install_as
    read_creds = credman_reader or default_extension_credman
    # FR #5659: passed -> CredMan -> SYSTEM for privileged writes only.
    import airc_identity as _ident
    import airc_passed_cred as _pcred
    # Default: live Windows/Samba classify. Tests may inject is_windows_host.
    # When only read_forcelist is injected (no is_windows_host), assume Windows
    # so unit hosts are not classified against the real network.
    if is_windows_host is None:
        if read_forcelist is None:
            is_windows_host = default_is_windows_host
        else:
            is_windows_host = lambda _h: True  # noqa: E731
    # FR #5661: SMB/ICMP probes for classified fallback errors.
    probe_tcp = tcp_probe or tcp_port_open

    def _smb_ok(h: str) -> bool:
        try:
            return bool(probe_tcp(h, 445))
        except TypeError:
            try:
                return bool(probe_tcp(h))
            except Exception:
                return False
        except Exception:
            return False

    def _fail_row(h: str, exc: BaseException | None, icmp: bool | None) -> dict[str, Any]:
        diag = classify_extension_host_error(
            exc, icmp_ok=icmp, smb_ok=_smb_ok(h)
        )
        return {"host": h, "ok": False, **diag}

    writes = (action or "").strip().lower() in {"install", "forceinstall", "apply"}
    cred_id = str(_kw.get("cred_id") or "").strip().lower()
    passed = _kw.get("passed_cred")
    if passed is None and cred_id:
        passed = _pcred.GLOBAL_PASSED_CREDS.take(cred_id)
    passed_requested = bool(cred_id) or bool(_kw.get("passed_requested"))
    if passed_requested and not (
        isinstance(passed, dict)
        and str(passed.get("username") or "").strip()
        and str(passed.get("password") or "")
    ):
        return {
            "ok": False,
            "action": action,
            "whatif": bool(whatif),
            "error": "auth_failed",
            "identity": "passed",
            "identity_label": "passed (missing)",
            "hosts": [],
            "failures": [{"error": "auth_failed", "reason": "cred-missing"}],
        }

    def _ext_reader(tgt: str) -> dict[str, str]:
        try:
            got = (
                read_creds()
                if credman_reader is not None
                else _ident.default_credman_reader(tgt)
            ) or {}
        except Exception as exc:  # noqa: BLE001
            return {"__error__": type(exc).__name__}
        if not isinstance(got, dict):
            return {}
        return got

    if writes and not whatif:
        resolved = _ident.resolve_remote_identity(
            verb="extension",
            passed=passed if isinstance(passed, dict) else None,
            passed_requested=False,
            credman_target=CREDMAN_TARGET,
            credman_reader=_ext_reader,
        )
    else:
        # status / WhatIf: no CredMan probe (FR #5364 / #5659).
        resolved = _ident.resolve_remote_identity(
            verb="extension",
            passed=None,
            credman_target=CREDMAN_TARGET,
            credman_reader=lambda _t: {},
            system_fn=lambda: {"account": "SYSTEM", "username": "SYSTEM", "password": ""},
        )
    identity_meta = {
        "identity": resolved.source,
        "identity_label": resolved.label,
        "account": resolved.account,
    }
    if is_dc is None:
        dc_set = {str(x).lower() for x in (dc_enum or default_dc_hostnames)()}
        is_dc = lambda h: str(h).lower() in dc_set  # noqa: E731
    value = force_install_value(extension_id)
    hosts_out: list[dict[str, Any]] = []
    wrote = False
    for host in list(enum() or []):
        name = str(host or "").strip()
        if not name:
            continue
        if is_dc(name):
            hosts_out.append({"host": name, "ok": True, "skipped": "dc"})
            continue
        # FR #5661: ICMP informs classification; do not short-circuit as unreachable.
        icmp_ok = bool(ping(name))
        try:
            windows = bool(is_windows_host(name))
        except Exception:
            windows = False
        if not windows:
            hosts_out.append(
                {
                    "host": name,
                    "ok": True,
                    "skipped": "not_windows",
                    "would_write": False,
                }
            )
            continue
        if not writes or whatif:
            try:
                plan = probe_host_forcelist(
                    name, extension_id, reader=read_forcelist
                )
            except Exception as exc:
                hosts_out.append(_fail_row(name, exc, icmp_ok))
                continue
            would = bool(plan["would_write"])
            row: dict[str, Any] = {"host": name, "ok": True, "would_write": would}
            if not writes:
                row["skipped"] = "status" if would else "already"
            elif not would:
                row["skipped"] = "already"
            row["chrome"] = bool(plan["chrome_present"])
            row["edge"] = bool(plan["edge_present"])
            if not would:
                row["state"] = "present"
            hosts_out.append(row)
            continue
        # FR #5659: use resolved passed/credman identity first when available.
        use_as = resolved.source in (_ident.IDENTITY_PASSED, _ident.IDENTITY_CREDMAN)
        user = resolved.username if use_as else ""
        pw = resolved.password if use_as else ""
        try:
            if use_as and user and pw:
                chrome_w = _apply_wrote(apply_as, name, "chrome", value, user, pw)
                edge_w = _apply_wrote(apply_as, name, "edge", value, user, pw)
            else:
                chrome_w = _apply_wrote(apply, name, "chrome", value)
                edge_w = _apply_wrote(apply, name, "edge", value)
        except Exception as exc:
            # FR #5708: only true IPC/registry auth failures are auth_failed;
            # path-not-found (53/67) and other reach errors keep classified detail.
            if use_as and is_ipc_auth_failed(exc):
                hosts_out.append(
                    {
                        "host": name,
                        "ok": False,
                        "error": "auth_failed",
                        "identity": resolved.source,
                        "account": resolved.account,
                        "detail": str(exc)[:300],
                    }
                )
                continue
            if not is_access_denied(exc):
                hosts_out.append(_fail_row(name, exc, icmp_ok))
                continue
            # SYSTEM path access-denied: try CredMan once if not already used.
            creds = {}
            try:
                creds = read_creds() or {}
            except Exception:
                creds = {}
            cuser = str(creds.get("username") or "").strip()
            cpw = str(creds.get("password") or "")
            if not cuser or not cpw:
                hosts_out.append(
                    {
                        "host": name,
                        "ok": False,
                        "error": "system-access-denied",
                        "credman_missing": True,
                        **identity_meta,
                    }
                )
                continue
            try:
                chrome_w = _apply_wrote(apply_as, name, "chrome", value, cuser, cpw)
                edge_w = _apply_wrote(apply_as, name, "edge", value, cuser, cpw)
            except Exception as exc2:
                # FR #5659: CredMan access-denied is auth_failed (no silent fallback).
                # FR #5661 / #5708: other reach errors keep classified codes + detail.
                if is_ipc_auth_failed(exc2):
                    hosts_out.append(
                        {
                            "host": name,
                            "ok": False,
                            "error": "auth_failed",
                            "identity": "credman",
                            "detail": str(exc2)[:300],
                        }
                    )
                else:
                    hosts_out.append(_fail_row(name, exc2, icmp_ok))
                continue
            if chrome_w or edge_w:
                wrote = True
            hosts_out.append(
                {
                    "host": name,
                    "ok": True,
                    "chrome": chrome_w,
                    "edge": edge_w,
                    "auth": "credman",
                    "identity": "credman",
                    **(
                        {"skipped": "already", "state": "present"}
                        if not (chrome_w or edge_w)
                        else {}
                    ),
                }
            )
            continue
        if use_as:
            if chrome_w or edge_w:
                wrote = True
            hosts_out.append(
                {
                    "host": name,
                    "ok": True,
                    "chrome": chrome_w,
                    "edge": edge_w,
                    "auth": resolved.source,
                    "identity": resolved.source,
                    **(
                        {"skipped": "already", "state": "present"}
                        if not (chrome_w or edge_w)
                        else {}
                    ),
                }
            )
            continue
        if chrome_w or edge_w:
            wrote = True
        hosts_out.append(
            {
                "host": name,
                "ok": True,
                "chrome": chrome_w,
                "edge": edge_w,
                **(
                    {"skipped": "already", "state": "present"}
                    if not (chrome_w or edge_w)
                    else {}
                ),
            }
        )
    return {
        **identity_meta,
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "wrote_gpo": False,
        "wrote_registry": wrote,
        "extension_id": extension_id,
        "hosts": hosts_out,
    }



def run_extension_verb(
    *,
    action: str = "install",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    on_done: Callable[[ExtensionVerbResult], Any] | None = None,
    **_kw: Any,
) -> ExtensionVerbResult:
    """FR #5520: when wait=False, accept immediately and deliver DCC via on_done after worker."""
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or fill_holes_work
    bits = [
        "EXTENSION accepted",
        f"id={qid}",
        f"action={action}",
        f"extension={DEFAULT_EXTENSION_ID}",
        f"gpo={DEFAULT_GPO_NAME}",
    ]
    if whatif:
        bits.append("whatif=1")
    accepted = " ".join(bits)

    def _finish(data: dict[str, Any], *, reply: str | None = None) -> ExtensionVerbResult:
        res = ExtensionVerbResult(
            True, reply or accepted, job_id=qid, payload=data or None
        )
        if on_done is not None:
            on_done(res)
        return res

    def _call_work() -> dict[str, Any]:
        try:
            out = work(
                action=action,
                whatif=whatif,
                extension_id=DEFAULT_EXTENSION_ID,
                **_kw,
            )
        except TypeError:
            out = work(action=action, whatif=whatif, **_kw)
        return out if isinstance(out, dict) else {}

    def _safe() -> ExtensionVerbResult:
        try:
            last = _call_work()
        except Exception:
            last = {"ok": False, "gpo": "fail", "reason": "worker_exception"}
        reply = accepted
        if wait and last:
            parts = [accepted]
            gpo = str(last.get("gpo") or ("ok" if last.get("ok") else "fail"))
            parts.append(f"gpo_result={gpo}")
            if last.get("reason"):
                parts.append(f"reason={last.get('reason')}")
            browsers = last.get("browsers") or []
            if browsers:
                parts.append("browsers=" + ",".join(str(b) for b in browsers))
            reply = " ".join(parts)
        return _finish(last, reply=reply)

    if wait:
        return _safe()
    import airc_isolated as _iso

    if _iso.is_packaged_work(work):

        def _from_child(data: Any) -> None:
            # FR #5665: normalize death / isolated-fault before log build.
            if not isinstance(data, dict):
                payload = {
                    "ok": False,
                    "error": "worker_died",
                    "detail": "bad-payload",
                }
            else:
                payload = dict(data)
                import airc_isolated as _iso2

                if _iso2.is_worker_fault(payload):
                    detail = str(
                        payload.get("detail") or payload.get("error") or "no-result"
                    )[:300]
                    payload = {
                        "ok": False,
                        "error": "worker_died",
                        "detail": detail,
                    }
            _finish(payload)

        # FR #5522: child must run the same packaged worker (GPO then fill-holes
        # when service_extension_runner passes extension_gpo_then_fill_holes). Hard-coding
        # fill_holes_work skipped Invoke-AircExtensionGpo.ps1 after FR #5537 isolation.
        fn_name = getattr(work, "__name__", "") or "fill_holes_work"
        _iso.start_isolated(
            wait=False,
            run=_safe,
            packaged=(
                "airc_extension",
                fn_name,
                {
                    "action": action,
                    "whatif": bool(whatif),
                    "extension_id": DEFAULT_EXTENSION_ID,
                },
            ),
            name="airc-extension-worker",
            on_done=_from_child,
        )
    else:
        threading.Thread(target=_safe, name="airc-extension-worker", daemon=True).start()
    return ExtensionVerbResult(True, accepted, job_id=qid, payload=None)


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



def _format_gpo_log_block(gpo: dict[str, Any]) -> dict[str, Any]:
    """FR #5522 / #5586: honor attempted=False when the GPO step did not run.

    FR #5644 / MRB #5648: keep script triage fields so gpo_access_denied need=
    guidance and Access-denied error/dc/gpo_via reach the EXTENSION DCC log.
    """
    attempted = True if "attempted" not in gpo else bool(gpo.get("attempted"))
    out = {
        "attempted": attempted,
        "name": (gpo.get("gpo_name") or gpo.get("name") or DEFAULT_GPO_NAME),
        "ok": bool(gpo.get("ok")) if attempted else False,
        "result": gpo.get("gpo"),
        "browsers": list(gpo.get("browsers") or []),
        "policy_names": list(gpo.get("policy_names") or []),
        "reason": gpo.get("reason"),
        "wrote_gpo": bool(gpo.get("wrote_gpo")),
    }
    for key in (
        "error",
        "dc",
        "gpo_via",
        "exit_code",
        "need",
        "credman_tried",
        "credman_present",
    ):
        if gpo.get(key) is not None and gpo.get(key) != "":
            out[key] = gpo.get(key)
    return out


def build_extension_log(
    action: str,
    *,
    whatif: bool = False,
    hosts: list[dict] | None = None,
    failures: list[dict] | None = None,
    gpo: dict | None = None,
    fallback: dict | None = None,
    extra: dict | None = None,
    extension_id: str = DEFAULT_EXTENSION_ID,
) -> dict[str, Any]:
    # FR #5520: stub not-implemented only when there is no worker result at all.
    # Empty failures=[] after a real worker must stay empty (do not re-inject stub).
    has_worker = (
        gpo is not None
        or hosts is not None
        or failures is not None
        or fallback is not None
    )
    if not has_worker:
        fails = [{"step": "gpo", "error": "not-implemented-fr-b"}]
    else:
        fails = list(failures or [])
    if extra:
        fails = fails  # extra is scrubbed, never merged as secrets
    log = {
        "action": action,
        "whatif": bool(whatif),
        "extension_id": extension_id,
        "gpo": (_format_gpo_log_block(gpo) if isinstance(gpo, dict) else (gpo or {"attempted": False, "name": DEFAULT_GPO_NAME})),
        "fallback": fallback or {"attempted": False},
        "hosts": list(hosts or []),
        "failures": fails,
    }
    if extra:
        for k, v in extra.items():
            if not _SECRET_KEY_RE.search(str(k)):
                log[k] = v
    log = _scrub(log)
    log["failure_count"] = len(log.get("failures") or [])
    return log


def extension_log_from_payload(
    action: str,
    *,
    whatif: bool = False,
    payload: dict[str, Any] | None = None,
    extension_id: str = DEFAULT_EXTENSION_ID,
) -> dict[str, Any]:
    """FR #5520: build DCC log from worker payload (gpo_detail + hosts), not accept defaults.

    FR #5665: isolated worker_died / isolated-fault must not become
    gpo_step_skipped + empty hosts (fail-open empty success).
    """
    data = payload if isinstance(payload, dict) else {}
    err = str(data.get("error") or "").strip()
    err_l = err.lower()
    if err_l == "worker_died" or err_l.startswith("isolated-fault"):
        detail = str(data.get("detail") or err)[:300]
        return build_extension_log(
            action,
            whatif=whatif,
            hosts=[],
            failures=[
                {
                    "step": "worker",
                    "error": "worker_died",
                    "detail": detail or "no-result",
                }
            ],
            gpo={
                "ok": False,
                "attempted": False,
                "reason": "worker_died",
                "gpo_name": DEFAULT_GPO_NAME,
                "wrote_gpo": False,
            },
            fallback={"attempted": False},
            extension_id=extension_id or DEFAULT_EXTENSION_ID,
        )
    detail = data.get("gpo_detail")
    if isinstance(detail, dict):
        gpo = dict(detail)
        if "gpo" not in gpo and data.get("gpo") is not None:
            gpo["gpo"] = data.get("gpo")
        if "reason" not in gpo and data.get("gpo_reason") is not None:
            gpo["reason"] = data.get("gpo_reason")
    elif data and (
        data.get("gpo") is not None
        or data.get("gpo_reason") is not None
        or data.get("wrote_gpo")
        or data.get("policy_names")
    ):
        # Real GPO fields present without gpo_detail (legacy shape).
        gpo = {
            "ok": bool(data.get("ok")) if data.get("gpo") in {"ok", "present"} else bool(data.get("wrote_gpo")),
            "gpo": data.get("gpo"),
            "gpo_name": data.get("gpo_name") or DEFAULT_GPO_NAME,
            "browsers": list(data.get("browsers") or []),
            "policy_names": list(data.get("policy_names") or []),
            "reason": data.get("gpo_reason") or data.get("reason"),
            "wrote_gpo": bool(data.get("wrote_gpo")),
        }
    elif data:
        # FR #5586 / #5522: fill-holes-only payload --- GPO step did not run.
        gpo = {
            "ok": False,
            "gpo": None,
            "gpo_name": DEFAULT_GPO_NAME,
            "browsers": [],
            "policy_names": [],
            "reason": "gpo_step_skipped",
            "wrote_gpo": False,
            "attempted": False,
        }
    else:
        gpo = None
    hosts = list(data.get("hosts") or []) if data else None
    fails = list(data.get("failures") or []) if data else None
    if data and fails is not None and not fails:
        for h in hosts or []:
            if isinstance(h, dict) and h.get("error"):
                entry = {
                    "step": "fallback",
                    "host": h.get("host") or h.get("hostname"),
                    "error": h.get("error"),
                }
                # FR #5661: surface underlying OS/RPC text for operators.
                if h.get("detail"):
                    entry["detail"] = h.get("detail")
                fails.append(entry)
    # FR #5644 / MRB #5648: GPO step failure must appear in failures[].
    if data and fails is not None and isinstance(gpo, dict):
        gpo_attempted = True if "attempted" not in gpo else bool(gpo.get("attempted"))
        if gpo_attempted and not bool(gpo.get("ok")):
            if not any(isinstance(f, dict) and f.get("step") == "gpo" for f in fails):
                entry: dict[str, Any] = {
                    "step": "gpo",
                    "error": gpo.get("error") or gpo.get("reason") or "gpo_failed",
                }
                for key in ("dc", "gpo_via", "need"):
                    if gpo.get(key) is not None and gpo.get(key) != "":
                        entry[key] = gpo.get(key)
                fails.append(entry)
    fallback = data.get("fallback") if data else None
    if fallback is None and data:
        fallback = {"attempted": True, "host_count": len(hosts or [])}
    return build_extension_log(
        action,
        whatif=whatif,
        hosts=hosts,
        failures=fails,
        gpo=gpo,
        fallback=fallback,
        extension_id=extension_id or DEFAULT_EXTENSION_ID,
    )


def extension_log_bytes(log: dict[str, Any]) -> bytes:
    return (json.dumps(log, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def deliver_extension_log(
    *,
    job_id: str,
    log: dict[str, Any],
    offer: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    import airc_dcc_bulk as _dcc

    jid = (job_id or "").strip().lower() or "00000000"
    raw = extension_log_bytes(log)
    digest = hashlib.sha256(raw).hexdigest()
    nfail = int(log.get("failure_count") or 0)
    # FR #5644 / MRB #5648: non-zero DONE when failure_count > 0.
    exit_code = 0 if nfail == 0 else 1
    summary = f"EXTENSION log failures={nfail} action={log.get('action')} bytes={len(raw)}"
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(log.get("failures") or [], start=2):
        lines.append(f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}")
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload_bounded
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(
                jid, exit_code, nbytes=len(raw), sha256=digest, via="dcc"
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
            lines.append(f"err id={jid} seq={len(lines)+1} dcc failed: {exc}; falling back to IRC")
            lines.append("CONT id=" + jid + " offset=1")
            done = f"DONE id={jid} exit={exit_code} via=irc reason=dcc-fail"
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
    done = f"DONE id={jid} exit={exit_code} via=irc"
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
