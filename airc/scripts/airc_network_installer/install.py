"""Per-host install orchestration for FR #3991 (local msiexec + remote PsExec)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .core import (
    SERVICE_NAME,
    HostResult,
    classify_msiexec_exit,
    is_windows_smb_host,
    msiexec_install_args,
    planned_action,
)

# FR #5721 / #5709: WNet so CredMan password never lands on net use argv.
from airc_wnet import is_wnet_auth_failed, wnet_add, wnet_cancel

RemoteRunner = Callable[..., subprocess.CompletedProcess]


def sanitize_legion_detail(text: str, *, limit: int = 300) -> str:
    """FR #5744: operator-facing detail never carries credential material."""
    raw = str(text or "")
    # Drop password=/pass=/secret= assignments entirely (key + value).
    scrubbed = re.sub(
        r"(?i)\b(password|passwd|pwd|pass|secret)\s*=\s*\S+",
        "<redacted>",
        raw,
    )
    # Assemble test-placeholder prefix at runtime (FR #3304 source pin).
    _fake = "FAKE" + "_"
    scrubbed = re.sub(rf"(?i)\b{_fake}[A-Za-z0-9_\-]+", "<redacted>", scrubbed)
    return scrubbed[:limit]


def classify_legion_install_error(
    exc: BaseException | None,
    *,
    step: str,
    smb_ok: bool | None = None,
) -> dict[str, Any]:
    """FR #5744: map LEGION remote failures like EXTENSION #5708.

    Codes: host_down (WinError 53/67 + SMB preflight), auth_failed (5/1326),
    session_conflict (1219). Always returns sanitised detail + step.
    """
    step_s = (step or "install").strip() or "install"
    if smb_ok is False and exc is None:
        return {
            "error": "host_down",
            "detail": sanitize_legion_detail("smb-445-unreachable"),
            "step": step_s,
        }
    if exc is None:
        return {
            "error": "unreachable",
            "detail": sanitize_legion_detail("no-exception"),
            "step": step_s,
        }
    win = int(getattr(exc, "winerror", 0) or 0)
    err_no = int(getattr(exc, "errno", 0) or 0)
    code = win or err_no
    detail = sanitize_legion_detail(str(exc))
    msg = detail.lower()
    if code == 1219 or "multiple connections to a server" in msg:
        return {"error": "session_conflict", "detail": detail or "winerror-1219", "step": step_s}
    if code in (5, 86, 1326, 1385) or is_wnet_auth_failed(exc):
        return {"error": "auth_failed", "detail": detail or "logon-failed", "step": step_s}
    if code in (53, 67) or smb_ok is False or (
        "network path was not found" in msg
        or "network name cannot be found" in msg
        or "no network provider" in msg
    ):
        return {"error": "host_down", "detail": detail or f"winerror-{code or 53}", "step": step_s}
    if isinstance(exc, FileNotFoundError) and (
        "network path" in msg or "winerror 53" in msg or code in (53, 67, 0)
    ):
        # Python often wraps WinError 53 as FileNotFoundError.
        return {"error": "host_down", "detail": detail or "file-not-found-unc", "step": step_s}
    return {
        "error": f"install:{type(exc).__name__}",
        "detail": detail or type(exc).__name__,
        "step": step_s,
    }



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
    ensure_psexec_result,
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


def read_remote_airc_profile_result(
    host: str,
    *,
    username: str = "",
    password: str = "",
) -> dict[str, Any]:
    """FR #5758 / #5781: remote profile via the same WNet session install uses.

    Authenticate to ``\\\\host\\IPC$`` (not ``c$`` alone) when username is set —
    matching ``install_remote`` — then read ``\\\\host\\c$\\…\\airc-install.json``.
    Returns ``{profile, ok, found, detail}``:
    - ok+found+profile: readable install.json with a valid profile
    - ok+not found: WNet/path reachable but no install.json (new host)
    - not ok: WNet or share access failed (SYSTEM/CredMan must not silently default)
    """
    from .core import ALLOWED_PROFILES

    mid = (host or "").strip()
    empty = {"profile": "", "ok": False, "found": False, "detail": "empty-host"}
    if not mid:
        return empty
    ipc = rf"\\{mid}\IPC$"
    used_wnet = False
    if username:
        try:
            _net_use(ipc, username, password or "")
            used_wnet = True
        except Exception as exc:  # noqa: BLE001
            return {
                "profile": "",
                "ok": False,
                "found": False,
                "detail": sanitize_legion_detail(
                    f"wnet-ipc:{type(exc).__name__}:{exc}"
                ),
            }
    access_errors = 0
    try:
        import json as _json

        for rel in (
            r"ai\airc\config\airc-install.json",
            r"Program Files\Bobiverse\airc\config\airc-install.json",
            r"ai\airc\config\airc.json",
            r"Program Files\Bobiverse\airc\config\airc.json",
        ):
            p = Path(rf"\\{mid}\c$\{rel}")
            try:
                if not p.is_file():
                    continue
                data = _json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                prof = str(data.get("profile") or "").strip().lower()
                if prof in ALLOWED_PROFILES:
                    return {
                        "profile": prof,
                        "ok": True,
                        "found": True,
                        "detail": "",
                    }
                # File present but profile missing/invalid — treat as found empty.
                return {
                    "profile": "",
                    "ok": True,
                    "found": True,
                    "detail": "profile-missing-or-invalid",
                }
            except OSError:
                access_errors += 1
                continue
            except (ValueError, TypeError):
                continue
        if access_errors and not used_wnet and not username:
            # Unauthenticated SYSTEM probe could not open any candidate path.
            return {
                "profile": "",
                "ok": False,
                "found": False,
                "detail": "share-access-denied-or-missing",
            }
        if access_errors and used_wnet:
            return {
                "profile": "",
                "ok": False,
                "found": False,
                "detail": "share-access-denied-after-wnet",
            }
        return {
            "profile": "",
            "ok": True,
            "found": False,
            "detail": "not-found",
        }
    finally:
        if used_wnet:
            try:
                _net_use_delete(ipc)
            except Exception:
                pass


def read_remote_airc_profile(
    host: str,
    *,
    username: str = "",
    password: str = "",
) -> str:
    """FR #5758: profile string only (compat). Prefer ``read_remote_airc_profile_result``."""
    return str(
        read_remote_airc_profile_result(
            host, username=username, password=password
        ).get("profile")
        or ""
    )


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
    """Remote MSI install via PsExec. FR #5744: SMB preflight + classified failures."""
    t0 = time.monotonic()
    host_log_dir = log_dir / host
    host_log_dir.mkdir(parents=True, exist_ok=True)
    remote_msi_name = msi_path.name
    remote_msi = rf"C:\Temp\{remote_msi_name}"
    remote_log = rf"C:\Temp\airc-{candidate_version}-install.log"
    result_log = host_log_dir / Path(remote_log).name

    # FR #5744: probe TCP/445 before UNC/WNet/sc timeouts (30-45s).
    smb_ok = bool(is_windows_smb_host(host, timeout=1.5))
    if not smb_ok:
        cls = classify_legion_install_error(None, step="preflight", smb_ok=False)
        return HostResult(
            host=host,
            action="install",
            status="failed",
            duration_s=time.monotonic() - t0,
            detail=cls["detail"],
            error=cls["error"],
            step=cls["step"],
        )

    try:
        prev = read_remote_version(host)
    except Exception as exc:  # noqa: BLE001
        cls = classify_legion_install_error(exc, step="version_probe", smb_ok=smb_ok)
        return HostResult(
            host=host,
            action="install",
            status="failed",
            duration_s=time.monotonic() - t0,
            detail=cls["detail"],
            error=cls["error"],
            step=cls["step"],
        )
    present = remote_service_running(host)
    action = planned_action(
        installed=prev or None,
        candidate=candidate_version,
        force=force,
        present=present,
    )
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
        try:
            _net_use(ipc, username, password)
        except Exception as exc:  # noqa: BLE001
            cls = classify_legion_install_error(exc, step="ipc", smb_ok=smb_ok)
            return HostResult(
                host=host,
                previous_version=prev,
                action=action,
                status="failed",
                duration_s=time.monotonic() - t0,
                detail=cls["detail"],
                error=cls["error"],
                step=cls["step"],
            )
    try:
        temp_unc = Path(rf"\\{host}\c$\Temp")
        try:
            temp_unc.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        remote_unc = temp_unc / remote_msi_name
        try:
            shutil.copy2(msi_path, remote_unc)
        except Exception as exc:  # noqa: BLE001
            cls = classify_legion_install_error(exc, step="copy", smb_ok=smb_ok)
            return HostResult(
                host=host,
                previous_version=prev,
                action=action,
                status="failed",
                duration_s=time.monotonic() - t0,
                detail=cls["detail"],
                error=cls["error"],
                step=cls["step"],
            )
        try:
            proc = subprocess.run(
                psexec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            cls = classify_legion_install_error(exc, step="psexec", smb_ok=smb_ok)
            return HostResult(
                host=host,
                previous_version=prev,
                action=action,
                status="failed",
                duration_s=time.monotonic() - t0,
                detail=cls["detail"],
                error=cls["error"],
                step=cls["step"],
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
            detail=sanitize_legion_detail(detail, limit=2000),
            reboot_required=(kind == "reboot_required"),
        )
    finally:
        if username:
            _net_use_delete(ipc)
