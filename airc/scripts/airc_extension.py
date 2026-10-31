"""Airc EXTENSION verb + isolated worker (FR #5290 / #5291 / #5292 / #5293 / #5520).

FR-A: verb + isolated worker. FR-B: DC + GPO Priority-web-extension.
FR-C: LDAP enum + per-host Chrome/Edge ForceInstall fallback (always after GPO).
FR #5364: machine account first; CredMan PriorityAirc/ExtensionAdmin on access-denied.
FR-D: structured log via DCCLISTEN or IRC CONT.
FR #5520: DCC log joins worker via on_done (do not build from accept defaults).
Auth matches UPDATE. Never secrets on IRC.
"""
from __future__ import annotations

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
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?EXTENSION\s+(install|status)(?P<rest>.*)$"
)


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
    rest = m.group("rest") or ""
    return {
        "qid": (m.group(1) or "").lower(),
        "action": m.group(2).lower(),
        "whatif": bool(re.search(r"(?i)-WhatIf", rest)),
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


def next_forcelist_name(
    existing_names: list[str],
    existing_values: list[str],
    extension_id: str,
) -> str | None:
    """FR #5538: next unused 1,2,3... or None if the extension id is already present."""
    ext = (extension_id or "").strip()
    if ext and any(ext in str(v) for v in existing_values):
        return None
    used = {str(n) for n in existing_names}
    n = 1
    while str(n) in used:
        n += 1
    return str(n)


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
) -> None:
    """Retry registry write after IPC$ with CredMan user. Never log the secret."""
    import shutil
    import subprocess

    net = shutil.which("net")
    if not net:
        raise OSError(5, "net-missing")
    ipc = r"\\{0}\IPC$".format(host)
    try:
        p = subprocess.run(
            [net, "use", ipc, password, "/user:" + username],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if p.returncode != 0:
            raise OSError(5, "credman-ipc-failed")
        default_apply_force_install(host, product, value)
    finally:
        subprocess.run(
            [net, "use", ipc, "/delete", "/y"],
            capture_output=True,
            timeout=10,
        )


def default_apply_force_install(host: str, product: str, value: str) -> None:
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
                return
            winreg.SetValueEx(key, slot, 0, winreg.REG_SZ, value)
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
    apply_force_install_as: Callable[..., None] | None = None,
    credman_reader: Callable[[], dict[str, str]] | None = None,
    extra_hosts: list[str] | None = None,
    is_dc: Callable[[str], bool] | None = None,
    dc_enum: Callable[[], list[str]] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """FR #5292: LDAP enum + per-host Chrome/Edge ForceInstall. Never uses extra_hosts.

    FR #5364: on access-denied, retry with CredMan PriorityAirc/ExtensionAdmin.
    FR #5538: status is read-only; skip DCs; append a free forcelist name.
    """
    _ = extra_hosts
    enum = ldap_enum or default_ldap_enum
    ping = ping_host or default_ping_host
    apply = apply_force_install or default_apply_force_install
    apply_as = apply_force_install_as or default_apply_force_install_as
    read_creds = credman_reader or default_extension_credman
    writes = (action or "").strip().lower() in {"install", "forceinstall", "apply"}
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
        if not ping(name):
            hosts_out.append({"host": name, "ok": False, "error": "unreachable"})
            continue
        if not writes:
            hosts_out.append(
                {"host": name, "ok": True, "would_write": True, "skipped": "status"}
            )
            continue
        if whatif:
            hosts_out.append({"host": name, "ok": True, "would_write": True})
            continue
        try:
            apply(name, "chrome", value)
            apply(name, "edge", value)
        except Exception as exc:
            if not is_access_denied(exc):
                hosts_out.append(
                    {"host": name, "ok": False, "error": type(exc).__name__}
                )
                continue
            creds = {}
            try:
                creds = read_creds() or {}
            except Exception:
                creds = {}
            user = str(creds.get("username") or "").strip()
            pw = str(creds.get("password") or "")
            if not user or not pw:
                hosts_out.append(
                    {"host": name, "ok": False, "error": "credman-missing"}
                )
                continue
            try:
                apply_as(name, "chrome", value, user, pw)
                apply_as(name, "edge", value, user, pw)
            except Exception as exc2:
                hosts_out.append(
                    {"host": name, "ok": False, "error": type(exc2).__name__}
                )
                continue
            wrote = True
            hosts_out.append(
                {
                    "host": name,
                    "ok": True,
                    "chrome": True,
                    "edge": True,
                    "auth": "credman",
                }
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
            payload = data if isinstance(data, dict) else {
                "ok": False,
                "gpo": "fail",
                "reason": "isolated-fault",
            }
            _finish(payload)

        _iso.start_isolated(
            wait=False,
            run=_safe,
            packaged=(
                "airc_extension",
                "fill_holes_work",
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
        "gpo": ({"attempted": True, "name": (gpo.get("gpo_name") or gpo.get("name") or DEFAULT_GPO_NAME), "ok": bool(gpo.get("ok")), "result": gpo.get("gpo"), "browsers": list(gpo.get("browsers") or []), "policy_names": list(gpo.get("policy_names") or []), "reason": gpo.get("reason"), "wrote_gpo": bool(gpo.get("wrote_gpo"))} if isinstance(gpo, dict) else (gpo or {"attempted": False, "name": DEFAULT_GPO_NAME})),
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
    """FR #5520: build DCC log from worker payload (gpo_detail + hosts), not accept defaults."""
    data = payload if isinstance(payload, dict) else {}
    detail = data.get("gpo_detail")
    if isinstance(detail, dict):
        gpo = dict(detail)
        if "gpo" not in gpo and data.get("gpo") is not None:
            gpo["gpo"] = data.get("gpo")
        if "reason" not in gpo and data.get("gpo_reason") is not None:
            gpo["reason"] = data.get("gpo_reason")
    elif data:
        gpo = {
            "ok": bool(data.get("ok")),
            "gpo": data.get("gpo"),
            "gpo_name": data.get("gpo_name") or DEFAULT_GPO_NAME,
            "browsers": list(data.get("browsers") or []),
            "policy_names": list(data.get("policy_names") or []),
            "reason": data.get("gpo_reason") or data.get("reason"),
            "wrote_gpo": bool(data.get("wrote_gpo")),
        }
    else:
        gpo = None
    hosts = list(data.get("hosts") or []) if data else None
    fails = list(data.get("failures") or []) if data else None
    if data and fails is not None and not fails:
        for h in hosts or []:
            if isinstance(h, dict) and h.get("error"):
                fails.append(
                    {
                        "step": "fallback",
                        "host": h.get("host") or h.get("hostname"),
                        "error": h.get("error"),
                    }
                )
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
    summary = f"EXTENSION log failures={nfail} action={log.get('action')} bytes={len(raw)}"
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(log.get("failures") or [], start=2):
        lines.append(f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}")
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(jid, 0, nbytes=len(raw), sha256=digest, via="dcc")
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
