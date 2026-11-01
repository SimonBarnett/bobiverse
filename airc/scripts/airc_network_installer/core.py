"""Pure helpers for FR #3991 airc-network-installer (testable without SMB/PsExec)."""

from __future__ import annotations

import csv
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SERVICE_NAME = "Airc"
AIRC_PROFILE_PROPERTY = "AIRC_PROFILE"
DEFAULT_PROFILE = "client"
ALLOWED_PROFILES = frozenset({"fleet", "client", "workstation"})
REPO = "SimonBarnett/bobiverse"
AIRC_ASSET_PREFIX = "airc-"
SMB_PORT = 445

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(raw: Optional[str]) -> tuple[int, ...]:
    """Parse DisplayVersion / VERSION file into a comparable tuple."""
    if not raw:
        return (0,)
    m = _VERSION_RE.search(str(raw).strip())
    if not m:
        return (0,)
    parts = [int(p) if p is not None else 0 for p in m.groups() if p is not None]
    return tuple(parts) if parts else (0,)


def compare_versions(installed: Optional[str], candidate: Optional[str]) -> int:
    """Return -1 if installed < candidate, 0 if equal, 1 if installed > candidate."""
    a = parse_version(installed)
    b = parse_version(candidate)
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def planned_action(
    *,
    installed: Optional[str],
    candidate: str,
    force: bool = False,
    present: bool = False,
) -> str:
    """Return install|upgrade|skip for one host."""
    if force:
        return "install" if not present and not installed else "upgrade"
    if not present and not installed:
        return "install"
    if compare_versions(installed, candidate) < 0:
        return "upgrade"
    return "skip"


def classify_msiexec_exit(code: int) -> str:
    """success|reboot_required|failed for an msiexec exit code."""
    if code == 0:
        return "success"
    if code == 3010:
        return "reboot_required"
    return "failed"


def msiexec_install_args(
    *,
    msi_local_path: str,
    log_local_path: str,
    profile: str = DEFAULT_PROFILE,
) -> list[str]:
    """Exact msiexec argv for remote/local quiet install (FR #3991)."""
    prof = (profile or DEFAULT_PROFILE).strip().lower()
    if prof not in ALLOWED_PROFILES:
        raise ValueError(f"unsupported profile {profile!r}; use fleet|client|workstation")
    return [
        "msiexec.exe",
        "/i",
        msi_local_path,
        "/qn",
        "/norestart",
        f"/l*v",
        log_local_path,
        f"{AIRC_PROFILE_PROPERTY}={prof}",
    ]


def parse_hosts_csv(raw: str) -> list[str]:
    """Split comma/semicolon/whitespace host list; strip empties."""
    if not raw:
        return []
    parts = re.split(r"[,;\s]+", str(raw).strip())
    return [p for p in (x.strip() for x in parts) if p]


def parse_hosts_file(path: Path) -> list[str]:
    lines: list[str] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            lines.extend(parse_hosts_csv(s))
    return lines


def dedupe_hosts(hosts: Iterable[str], *, local_names: Optional[Iterable[str]] = None) -> list[str]:
    """Preserve order; fold local aliases to a single local entry first when present."""
    local_set = {h.lower() for h in (local_names or [])}
    out: list[str] = []
    seen: set[str] = set()
    local_kept = False
    for h in hosts:
        key = h.lower()
        if key in local_set:
            if local_kept:
                continue
            local_kept = True
            # Prefer hostname form if available
            canon = next((x for x in (local_names or []) if x), h)
            if canon.lower() not in seen:
                out.append(canon)
                seen.add(canon.lower())
            continue
        if key not in seen:
            out.append(h)
            seen.add(key)
    return out


def is_windows_smb_host(host: str, *, timeout: float = 0.4) -> bool:
    """TCP/445 open is a weak Windows SMB signal; caller may reverse-DNS."""
    try:
        with socket.create_connection((host, SMB_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def reverse_dns(ip: str) -> str:
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name.rstrip(".")
    except OSError:
        return ip


def hosts_from_cidr(cidr: str, *, workers: int = 64) -> list[str]:
    """Scan CIDR for SMB; return reverse-DNS hostnames when possible."""
    net = ipaddress.IPv4Network(cidr, strict=False)
    found: list[str] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    hosts = [str(ip) for ip in net.hosts()]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(is_windows_smb_host, ip): ip for ip in hosts}
        for fut in as_completed(futs):
            ip = futs[fut]
            try:
                if fut.result():
                    found.append(reverse_dns(ip))
            except Exception:
                pass
    return sorted(set(found), key=lambda h: h.lower())


@dataclass
class HostResult:
    host: str
    previous_version: str = ""
    action: str = ""
    exit_code: Optional[int] = None
    status: str = ""
    duration_s: float = 0.0
    log_path: str = ""
    detail: str = ""
    reboot_required: bool = False
    # FR #5744: classified remote failure (host_down / auth_failed / session_conflict).
    error: str = ""
    step: str = ""


def write_summary_csv(path: Path, rows: list[HostResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "host",
                "previous_version",
                "action",
                "exit_code",
                "status",
                "duration_s",
                "log_path",
                "reboot_required",
                "detail",
                "error",
                "step",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "host": r.host,
                    "previous_version": r.previous_version,
                    "action": r.action,
                    "exit_code": r.exit_code if r.exit_code is not None else "",
                    "status": r.status,
                    "duration_s": f"{r.duration_s:.1f}",
                    "log_path": r.log_path,
                    "reboot_required": "1" if r.reboot_required else "0",
                    "detail": r.detail,
                    "error": r.error,
                    "step": r.step,
                }
            )


def assert_password_not_in_argv(argv: list[str], password: str) -> None:
    """Test helper: password must never appear as an argv token."""
    if not password:
        return
    for tok in argv:
        if password and password in str(tok):
            raise AssertionError("password leaked into argv")
