"""Per-host install orchestration for FR #3991 (local msiexec + remote PsExec)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .core import (
    SERVICE_NAME,
    HostResult,
    classify_msiexec_exit,
    msiexec_install_args,
    planned_action,
)

# FR #5721 / #5709: WNet so CredMan password never lands on net use argv.
from airc_wnet import wnet_add, wnet_cancel

RemoteRunner = Callable[..., subprocess.CompletedProcess]

# FR #5655 / #5712 / #5737: Sysinternals PsExec — never MSI-bundled (license).
# Install/UPDATE deploys with pinned SHA-256; LEGION uses/redeploys local cache only.
from .psexec_deploy import (  # noqa: E402
    PSEXEC_EXE_SHA256,
    PSEXEC_ZIP_SHA256,
    PSEXEC_ZIP_URL,
    _psexec_download_opted_out,
    cache_zip_path,
    deploy_psexec,
    ensure_psexec,
    find_psexec,
    load_psexec_pin,
    offer_download_psexec,
    plan_psexec,
    psexec_dest as _psexec_dest,
    psexec_hash_ok,
    redeploy_psexec_from_cache,
)

PSEXEC_PROBE_TIMEOUT_S = 8.0


def probe_psexec_source(
    url: str = PSEXEC_ZIP_URL,
    *,
    timeout: float = PSEXEC_PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Legacy FR #5712 probe kept for callers; LEGION plan no longer uses it."""
    import urllib.error
    import urllib.request

    target = (url or PSEXEC_ZIP_URL).strip() or PSEXEC_ZIP_URL
    ua = "bobiverse-airc-legion/1.0 (+https://github.com/SimonBarnett/bobiverse)"

    def _one(method: str) -> dict[str, Any]:
        req = urllib.request.Request(
            target,
            method=method,
            headers={"User-Agent": ua},
        )
        try:
            with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                code = int(getattr(resp, "status", None) or resp.getcode() or 0)
                if code >= 400:
                    return {"ok": False, "reason": f"http-{code}"}
                return {"ok": True, "reason": f"http-{code or 200}"}
        except urllib.error.HTTPError as exc:
            code = int(exc.code or 0)
            if method == "HEAD" and code in (405, 501):
                return {"ok": False, "reason": f"http-{code}", "retry_get": True}
            return {"ok": False, "reason": f"http-{code}"}
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}:{exc}"[:160]
            return {"ok": False, "reason": msg}

    first = _one("HEAD")
    if first.get("ok"):
        return {"reachable": True, "reason": str(first.get("reason") or "ok"), "url": target}
    if first.get("retry_get"):
        second = _one("GET")
        if second.get("ok"):
            return {
                "reachable": True,
                "reason": str(second.get("reason") or "ok"),
                "url": target,
            }
        return {
            "reachable": False,
            "reason": str(second.get("reason") or first.get("reason") or "unreachable"),
            "url": target,
        }
    return {
        "reachable": False,
        "reason": str(first.get("reason") or "unreachable"),
        "url": target,
    }

def read_local_version(install_root: Optional[Path] = None) -> str:
    roots = []
    if install_root:
        roots.append(install_root)
    roots.append(Path(r"C:\ai\airc"))
    env_root = os.environ.get("AIRC_INSTALL_ROOT") or os.environ.get("BOBIVERSE_AIRC_ROOT")
    if env_root:
        roots.insert(0, Path(env_root))
    for root in roots:
        ver = root / "VERSION"
        if ver.is_file():
            return ver.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    return ""


def service_running(name: str = SERVICE_NAME) -> bool:
    try:
        r = subprocess.run(
            ["sc", "query", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).upper()
        return r.returncode == 0 and "RUNNING" in out
    except Exception:
        return False


def remote_service_running(host: str, name: str = SERVICE_NAME) -> bool:
    try:
        r = subprocess.run(
            ["sc", f"\\\\{host}", "query", name],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).upper()
        if "1060" in out or "DOES NOT EXIST" in out:
            return False
        return r.returncode == 0 and ("STATE" in out or "SERVICE_NAME" in out)
    except Exception:
        return False


def read_remote_version(host: str) -> str:
    """Best-effort VERSION over admin share."""
    for rel in (r"ai\airc\VERSION", r"Program Files\Bobiverse\airc\VERSION"):
        p = Path(rf"\\{host}\c$\{rel}")
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        except OSError:
            continue
    return ""


def _net_use(unc: str, username: str, password: str) -> None:
    """Authenticate to ``unc`` via WNet (FR #5721). Password never on argv / 4688."""
    wnet_add(unc, username or "", password or "")


def _net_use_delete(unc: str) -> None:
    """Drop the WNet connection for ``unc`` (FR #5721)."""
    wnet_cancel(unc or "")


def install_local(
    *,
    msi_path: Path,
    candidate_version: str,
    profile: str,
    force: bool,
    log_dir: Path,
    dry_run: bool = False,
) -> HostResult:
    host = socket_hostname()
    t0 = time.monotonic()
    prev = read_local_version()
    present = service_running()
    action = planned_action(
        installed=prev or None,
        candidate=candidate_version,
        force=force,
        present=present,
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    host_log_dir = log_dir / host
    host_log_dir.mkdir(parents=True, exist_ok=True)
    local_log = Path(r"C:\Temp") / f"airc-{candidate_version}-install.log"
    result_log = host_log_dir / local_log.name
    if action == "skip" and not force:
        return HostResult(
            host=host,
            previous_version=prev,
            action="skip",
            status="skipped",
            duration_s=time.monotonic() - t0,
            detail="same or newer already installed",
        )
    args = msiexec_install_args(
        msi_local_path=str(msi_path),
        log_local_path=str(local_log),
        profile=profile,
    )
    if dry_run:
        return HostResult(
            host=host,
            previous_version=prev,
            action=action,
            status="dry-run",
            duration_s=time.monotonic() - t0,
            detail=" ".join(args),
        )
    local_log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(args, capture_output=True, text=True, timeout=900, check=False)
    code = int(proc.returncode)
    kind = classify_msiexec_exit(code)
    try:
        if local_log.is_file():
            shutil.copy2(local_log, result_log)
    except OSError:
        pass
    ok = kind in ("success", "reboot_required")
    post_ok = service_running() if ok else False
    detail = f"msiexec exit {code}"
    if ok and not post_ok:
        detail += "; service not RUNNING after install"
        ok = False
        kind = "failed"
    return HostResult(
        host=host,
        previous_version=prev,
        action=action,
        exit_code=code,
        status=kind if ok or kind == "reboot_required" else "failed",
        duration_s=time.monotonic() - t0,
        log_path=str(result_log),
        detail=detail,
        reboot_required=(kind == "reboot_required"),
    )


def socket_hostname() -> str:
    import socket

    return socket.gethostname()


def install_remote(
    *,
    host: str,
    msi_path: Path,
    candidate_version: str,
    profile: str,
    force: bool,
    psexec: str,
    username: str,
    password: str,
    log_dir: Path,
    dry_run: bool = False,
    timeout_s: float = 900.0,
) -> HostResult:
    t0 = time.monotonic()
    prev = read_remote_version(host)
    present = remote_service_running(host)
    action = planned_action(
        installed=prev or None,
        candidate=candidate_version,
        force=force,
        present=present,
    )
    host_log_dir = log_dir / host
    host_log_dir.mkdir(parents=True, exist_ok=True)
    remote_msi_name = msi_path.name
    remote_msi = rf"C:\Temp\{remote_msi_name}"
    remote_log = rf"C:\Temp\airc-{candidate_version}-install.log"
    result_log = host_log_dir / Path(remote_log).name
    if action == "skip" and not force:
        return HostResult(
            host=host,
            previous_version=prev,
            action="skip",
            status="skipped",
            duration_s=time.monotonic() - t0,
            detail="same or newer already installed",
        )
    msiexec = msiexec_install_args(
        msi_local_path=remote_msi,
        log_local_path=remote_log,
        profile=profile,
    )
    # PsExec without -u/-p: authenticate via net use so password stays out of PsExec argv.
    psexec_cmd = [
        psexec,
        rf"\\{host}",
        "-accepteula",
        "-h",
        "-s",
        *msiexec,
    ]
    if dry_run:
        return HostResult(
            host=host,
            previous_version=prev,
            action=action,
            status="dry-run",
            duration_s=time.monotonic() - t0,
            detail=" ".join(psexec_cmd),
        )
    ipc = rf"\\{host}\IPC$"
    if username:
        _net_use(ipc, username, password)
    try:
        temp_unc = Path(rf"\\{host}\c$\Temp")
        try:
            temp_unc.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        remote_unc = temp_unc / remote_msi_name
        try:
            shutil.copy2(msi_path, remote_unc)
        except Exception as exc:
            return HostResult(
                host=host,
                previous_version=prev,
                action=action,
                status="failed",
                duration_s=time.monotonic() - t0,
                detail=f"copy failed: {exc}",
            )
        proc = subprocess.run(
            psexec_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        code = int(proc.returncode)
        kind = classify_msiexec_exit(code)
        # Pull log back
        try:
            src_log = Path(rf"\\{host}\c$\Temp") / Path(remote_log).name
            if src_log.is_file():
                shutil.copy2(src_log, result_log)
        except OSError:
            pass
        ok = kind in ("success", "reboot_required")
        post_ok = remote_service_running(host) if ok else False
        detail = f"msiexec exit {code}"
        if ok and not post_ok:
            detail += "; service not RUNNING after install"
            ok = False
            kind = "failed"
        if not ok and result_log.is_file():
            try:
                lines = result_log.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = "\n".join(lines[-30:])
                detail += "\n--- log tail ---\n" + tail
            except OSError:
                pass
        return HostResult(
            host=host,
            previous_version=prev,
            action=action,
            exit_code=code,
            status=kind if ok or kind == "reboot_required" else "failed",
            duration_s=time.monotonic() - t0,
            log_path=str(result_log),
            detail=detail,
            reboot_required=(kind == "reboot_required"),
        )
    finally:
        if username:
            _net_use_delete(ipc)
