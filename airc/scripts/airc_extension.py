"""Airc EXTENSION verb + isolated worker (FR #5290 / FR #5292).

FR-A: verb + isolated stub. FR-C: LDAP computer enum + per-host registry
ForceInstall fallback (no GPO in this module). Auth matches UPDATE.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_EXTENSION_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"
CHROME_WEB_STORE_UPDATE = "https://clients2.google.com/service/update2/crx"
CHROME_FORCE_KEY = r"SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist"
EDGE_FORCE_KEY = r"SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist"

_EXTENSION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?EXTENSION\s+(install|status)(?P<rest>.*)$"
)


@dataclass
class ExtensionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""

    def reply_text(self) -> str:
        return self.reply


def parse_extension_command(text: str) -> dict[str, Any] | None:
    m = _EXTENSION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    rest = m.group("rest") or ""
    return {
        "qid": (m.group(1) or "").lower(),
        "action": m.group(2).lower(),
        "whatif": bool(re.search(r"(?i)-WhatIf", rest)),
    }


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


def default_apply_force_install(host: str, product: str, value: str) -> None:
    import winreg

    key_path = CHROME_FORCE_KEY if product == "chrome" else EDGE_FORCE_KEY
    rem = winreg.ConnectRegistry(host, winreg.HKEY_LOCAL_MACHINE)
    try:
        key = winreg.CreateKey(rem, key_path)
        try:
            winreg.SetValueEx(key, "1", 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(key)
    finally:
        winreg.CloseKey(rem)


def fill_holes_work(
    action: str,
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
    ldap_enum: Callable[[], list[str]] | None = None,
    ping_host: Callable[[str], bool] | None = None,
    apply_force_install: Callable[[str, str, str], None] | None = None,
    extra_hosts: list[str] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5292: LDAP enum + per-host Chrome/Edge ForceInstall. Never uses extra_hosts."""
    _ = extra_hosts
    enum = ldap_enum or default_ldap_enum
    ping = ping_host or default_ping_host
    apply = apply_force_install or default_apply_force_install
    value = force_install_value(extension_id)
    hosts_out: list[dict[str, Any]] = []
    wrote = False
    for host in list(enum() or []):
        name = str(host or "").strip()
        if not name:
            continue
        if not ping(name):
            hosts_out.append({"host": name, "ok": False, "error": "unreachable"})
            continue
        if whatif:
            hosts_out.append({"host": name, "ok": True, "would_write": True})
            continue
        try:
            apply(name, "chrome", value)
            apply(name, "edge", value)
        except Exception as exc:
            hosts_out.append(
                {"host": name, "ok": False, "error": type(exc).__name__}
            )
            continue
        wrote = True
        hosts_out.append({"host": name, "ok": True, "chrome": True, "edge": True})
    return {
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
    **_kw: Any,
) -> ExtensionVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or fill_holes_work

    def _safe() -> None:
        try:
            work(
                action=action,
                whatif=whatif,
                extension_id=DEFAULT_EXTENSION_ID,
                **_kw,
            )
        except Exception:
            return

    if wait:
        _safe()
    else:
        threading.Thread(target=_safe, name="airc-extension-worker", daemon=True).start()
    bits = [
        "EXTENSION accepted",
        f"id={qid}",
        f"action={action}",
        f"extension={DEFAULT_EXTENSION_ID}",
    ]
    if whatif:
        bits.append("whatif=1")
    return ExtensionVerbResult(True, " ".join(bits), job_id=qid)
