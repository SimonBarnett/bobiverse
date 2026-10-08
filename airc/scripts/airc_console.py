#!/usr/bin/env python3
"""airc console service core (FR #253).

Installable Windows service: on ChanServ-registered ``#{machinename}`` sit as
``{machinename}_console``; otherwise lobby on ``#{domain_or_workgroup}`` as
``{machinename}`` / ``{machinename}_N``. Silent in channel. Authenticated
PRIVMSG sessions get a per-user console pipe.

Offline-testable: auth, channel naming, session lifecycle, silent policy.
Live IRC loop lives in ``airc_console_service.py``.
"""
from __future__ import annotations

import base64
import binascii
import fnmatch
import os
import re
import subprocess
import shutil
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
import json

from account_map import AccountMap, parse_message_tags
from airc_jobs import JobProtocol, parse_job_verb

NICK = "console"
IRC_NICK_MAX = 30
DEFAULT_SHELL = os.environ.get("COMSPEC") or "cmd.exe"
IRC_SAFE_PAYLOAD = 350
PSB64_MAX_CHARS = 24_000
SHELL_OUTPUT_MAX_BYTES = 64_000
SHELL_TIMEOUT_S = 120.0
# FR #2632: per-Query pending shell commands (beyond the one in flight). Overflow
# still fail-closes with busy DONE so Wait never hangs without a DONE (#2612).
SHELL_PENDING_MAX = 8
UPDATE_PRODUCTS = frozenset({"airc", "bob", "jeeves"})
SHELL_MODE_TOKENS = frozenset({"off", "operators"})
JOBS_TOKENS = frozenset({"off", "on"})
UPDATE_CAP_TOKENS = frozenset({"off", "on"})
_PRIVMSG_RE = re.compile(
    r"^:([^!\s]+)(?:![^@\s]*@\S+)?\s+PRIVMSG\s+(\S+)\s+:?(.*)$",
    re.IGNORECASE,
)
_CHANNEL_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_CTCP_PING_RE = re.compile(r"^\x01PING(?: (.*))?\x01\s*$", re.IGNORECASE | re.DOTALL)
_PING_CMD_RE = re.compile(r"^\s*ping(?:\s+(\S+))?\s*$", re.IGNORECASE)
# FR #77: UPDATE airc|bob|jeeves [version] — fleet MSI via detached updater only.
_UPDATE_CMD_RE = re.compile(
    r"^\s*UPDATE\s+(airc|bob|jeeves)(?:\s+v?(\d+\.\d+\.\d+))?\s*$",
    re.IGNORECASE,
)
# Issue #302: fleet ear nicks bob-{machine} are already authenticated; machine varies.
_BOB_FLEET_NICK_RE = re.compile(r"^bob-[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)

ShopProbeResult = Literal["registered", "missing", "unknown"]
MachineIdSource = Literal[
    "arg",
    "AIRC_CONSOLE_MACHINE",
    "BOB_MACHINE_ID",
    "COMPUTERNAME",
    "HOSTNAME",
    "default",
]


class MachineIdUnresolved(ValueError):
    """No explicit fleet machine id and hostname fallback was refused (FR #77)."""


def _sanitize_id(raw: str) -> str:
    cleaned = _CHANNEL_SAFE.sub("-", (raw or "").strip()).strip("-_")
    return (cleaned or "unknown").lower()


def resolve_machine_id(
    override: str | None = None,
    *,
    allow_hostname_fallback: bool = True,
) -> tuple[str, MachineIdSource]:
    """Canonical machine-id rule (FR #77).

    Order: explicit ``-MachineId`` / override, then ``AIRC_CONSOLE_MACHINE``,
    then ``BOB_MACHINE_ID``. Hostname (``COMPUTERNAME`` / ``HOSTNAME``) is only
    used when ``allow_hostname_fallback`` is true — callers must treat that as
    an explicit choice so the console does not silently join the wrong shop.
    """
    if override and str(override).strip():
        return _sanitize_id(str(override)), "arg"
    env_airc = (os.environ.get("AIRC_CONSOLE_MACHINE") or "").strip()
    if env_airc:
        return _sanitize_id(env_airc), "AIRC_CONSOLE_MACHINE"
    env_bob = (os.environ.get("BOB_MACHINE_ID") or "").strip()
    if env_bob:
        return _sanitize_id(env_bob), "BOB_MACHINE_ID"
    host = (os.environ.get("COMPUTERNAME") or "").strip()
    if host:
        if not allow_hostname_fallback:
            raise MachineIdUnresolved(
                "no -MachineId / AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID; "
                "refusing silent COMPUTERNAME fallback"
            )
        return _sanitize_id(host), "COMPUTERNAME"
    host2 = (os.environ.get("HOSTNAME") or "").strip()
    if host2:
        if not allow_hostname_fallback:
            raise MachineIdUnresolved(
                "no -MachineId / AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID; "
                "refusing silent HOSTNAME fallback"
            )
        return _sanitize_id(host2), "HOSTNAME"
    if not allow_hostname_fallback:
        raise MachineIdUnresolved("no machine id available")
    return "unknown", "default"


def machine_id(override: str | None = None) -> str:
    """Fleet shop id for ``#{machine}`` / ``{machine}_console``.

    Prefer explicit override, then ``AIRC_CONSOLE_MACHINE`` / ``BOB_MACHINE_ID``
    (fleet ids like ``ionos``), then Windows ``COMPUTERNAME``. Using bare
    COMPUTERNAME alone (e.g. ``WIN-MPRE8VI4U6U``) joins the wrong channel and
    looks like \"does not connect\" on ``#ionos`` / ``#flamingo``.
    """
    mid, _src = resolve_machine_id(override, allow_hostname_fallback=True)
    return mid


def parse_update_command(text: str) -> tuple[str, str | None] | None:
    """Return ``(product, version|None)`` for an allowlisted UPDATE verb, else None."""
    m = _UPDATE_CMD_RE.match(text or "")
    if not m:
        return None
    product = m.group(1).lower()
    if product not in UPDATE_PRODUCTS:
        return None
    return product, m.group(2)


@dataclass
class UpdateScheduleResult:
    ok: bool
    status: str
    detail: str = ""
    product: str = ""
    version: str | None = None

    def reply_line(self) -> str:
        ver = self.version or ""
        bits = [f"UPDATE {self.status}", f"product={self.product or '?'}"]
        if ver:
            bits.append(f"version={ver}")
        if self.detail:
            bits.append(self.detail)
        if self.ok:
            bits[0] = "UPDATE accepted"
            bits.insert(1, f"status={self.status}")
        return " ".join(bits)[:400]


def _is_frozen_airc_runtime() -> bool:
    """True under PyInstaller airc.exe (FR #2949)."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def resolve_fleet_update_install_root(explicit: str | None = None) -> str:
    """Install tree for UPDATE Check (frozen-aware; FR #2949).

    Prefer an explicit root when it already contains the updater. Otherwise
    re-resolve from ``sys.executable`` under frozen builds so ``_MEI*`` parents
    of ``__file__`` are never used as InstallRoot.
    """
    name = "Update-BobiverseService.ps1"

    def _has_updater(root: Path) -> bool:
        return (root / "scripts" / name).is_file() or (root / name).is_file()

    if explicit:
        exp = Path(explicit)
        if _has_updater(exp):
            return str(exp.resolve())
    if _is_frozen_airc_runtime():
        exe = Path(sys.executable).resolve()
        # Pack stages ``airc\\airc.exe`` under the install root.
        cand = exe.parent.parent if exe.parent.name.lower() == "airc" else exe.parent
        if _has_updater(cand):
            return str(cand.resolve())
        return str(cand.resolve())
    if explicit:
        return str(Path(explicit).resolve())
    # Source / staged: parent of scripts/ (product tree).
    return str(Path(__file__).resolve().parents[1])


def _find_update_bobiverse_script(install_root: str, updater_script: str | None = None) -> Path | None:
    """Locate Update-BobiverseService.ps1 under the install tree (FR #2949)."""
    name = "Update-BobiverseService.ps1"
    candidates: list[Path] = []
    if updater_script:
        candidates.append(Path(updater_script))
    root = Path(install_root)
    candidates.append(root / "scripts" / name)
    candidates.append(root / name)
    # Source tree / non-frozen fallbacks (never preferred under frozen _MEI).
    if not _is_frozen_airc_runtime():
        candidates.append(Path(__file__).resolve().parent / name)
        candidates.append(
            Path(__file__).resolve().parents[2] / "common" / "scripts" / name
        )
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0] if candidates else None


def schedule_fleet_update(
    product: str,
    version: str | None = None,
    *,
    install_root: str | None = None,
    service_name: str | None = None,
    updater_script: str | None = None,
    state_dir: str | None = None,
    dry_run: bool = False,
    no_spawn: bool = False,
) -> UpdateScheduleResult:
    """Schedule ``Update-BobiverseService.ps1 -Mode Check`` (detached apply).

    Never runs ``msiexec`` in this process. The Check mode writes a plan and
    starts a scheduled-task / WMI helper; msiexec lives only in Apply.
    """
    product = (product or "").strip().lower()
    if product not in UPDATE_PRODUCTS:
        return UpdateScheduleResult(False, "rejected-product", product=product, version=version)
    install_root = resolve_fleet_update_install_root(install_root)
    script = _find_update_bobiverse_script(install_root, updater_script)
    if script is None or not script.is_file():
        return UpdateScheduleResult(
            False,
            "updater-missing",
            detail=str(script or (Path(install_root) / "scripts" / "Update-BobiverseService.ps1")),
            product=product,
            version=version,
        )
    if not service_name:
        service_name = {"bob": "ircBob", "jeeves": "ircJeeves"}.get(product, "Airc")
    ps = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32\WindowsPowerShell\v1.0\powershell.exe"
    if not Path(ps).is_file():
        ps = shutil_which_powershell()
    args = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Product",
        product,
        "-Mode",
        "Check",
        "-InstallRoot",
        str(install_root),
        "-ServiceName",
        service_name,
        "-ForceCheck",
    ]
    if version:
        args += ["-TargetVersion", version]
    if state_dir:
        args += ["-StateDir", str(state_dir)]
    if dry_run:
        args.append("-DryRun")
    if no_spawn:
        args.append("-NoSpawn")
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    except Exception as e:  # noqa: BLE001 — surface to IRC as spawn-failed
        return UpdateScheduleResult(
            False,
            "spawn-failed",
            detail=type(e).__name__,
            product=product,
            version=version,
        )
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).lower()
    # Prefer updater log phrases when present in stdout (Write-Host).
    status = "check-ran"
    ok = p.returncode == 0
    for key in (
        "update-scheduled",
        "scheduled-nospawn",
        "would-update",
        "skipped-pending",
        "blocked-loop-guard",
        "skipped-optout",
        "asset-url-rejected",
        "no-matching-asset",
        "no-sha256-asset",
        "release-lookup-failed",
        "spawn-failed",
        "cooldown",
        "current",
        "throttled",
    ):
        if key in out.replace("result=", " "):
            status = key
            break
    if status in {"update-scheduled", "scheduled-nospawn", "would-update"}:
        ok = True
        if status == "would-update":
            status = "scheduled"
        elif status == "update-scheduled":
            status = "scheduled"
    elif status in {"skipped-pending", "blocked-loop-guard", "skipped-optout", "cooldown", "current"}:
        ok = False
    detail = ""
    for line in (p.stdout or "").splitlines()[::-1]:
        if "self-update:" in line.lower() or "result=" in line.lower():
            detail = line.strip()[:200]
            break
    if not detail and p.returncode != 0:
        detail = f"exit={p.returncode}"
    return UpdateScheduleResult(ok, status, detail=detail, product=product, version=version)


def shutil_which_powershell() -> str:
    import shutil

    return shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"


def shop_channel(machine: str | None = None) -> str:
    mid = machine_id(machine)
    return f"#{mid}"


def _fit_nick(stem: str, suffix: str = "") -> str:
    """Build an IRC nick <= IRC_NICK_MAX, preferring to keep ``suffix`` intact."""
    stem = (stem or "unknown").strip("-_") or "unknown"
    suffix = suffix or ""
    max_stem = IRC_NICK_MAX - len(suffix)
    if max_stem < 1:
        return (stem + suffix)[:IRC_NICK_MAX]
    return (stem[:max_stem] + suffix)[:IRC_NICK_MAX]


def machine_console_nick(machine: str | None = None) -> str:
    """Nick when ``#{machine}`` is ChanServ-registered: ``{machine}_console``."""
    mid = machine_id(machine)
    return _fit_nick(mid, "_console")


def domain_lobby_nick(machine: str | None = None, suffix: int | None = None) -> str:
    """Nick for domain/workgroup lobby: ``{machine}`` or ``{machine}_{n}`` (n>=1)."""
    mid = machine_id(machine)
    if suffix is None or int(suffix) <= 0:
        return _fit_nick(mid, "")
    return _fit_nick(mid, f"_{int(suffix)}")


def console_nick(machine: str | None = None, explicit: str | None = None) -> str:
    """IRC nick for the console seat.

    Default is ``{machine}_console`` (registered-shop / provisional connect).
    Pass explicit ``console`` only on a single-console network; ``auto`` uses default.
    """
    if explicit and explicit.strip() and explicit.strip().lower() != "auto":
        return explicit.strip()[:IRC_NICK_MAX]
    return machine_console_nick(machine)


def domain_or_workgroup_id(override: str | None = None) -> str:
    """Windows domain NetBIOS name, or workgroup, sanitized for ``#{id}``.

    Order: explicit / ``AIRC_CONSOLE_DOMAIN`` → ``USERDNSDOMAIN`` first label →
    ``USERDOMAIN`` when it differs from ``COMPUTERNAME`` → short NetGetJoinInformation
    probe → ``USERDOMAIN`` → ``workgroup``. Never blocks unbounded on WMI.
    """
    if override and override.strip():
        return _sanitize_id(override)
    env = (os.environ.get("AIRC_CONSOLE_DOMAIN") or "").strip()
    if env:
        return _sanitize_id(env)

    dns = (os.environ.get("USERDNSDOMAIN") or "").strip()
    if dns:
        return _sanitize_id(dns.split(".")[0])

    userdomain = (os.environ.get("USERDOMAIN") or "").strip()
    computer = (os.environ.get("COMPUTERNAME") or "").strip()
    if userdomain and computer and userdomain.upper() != computer.upper():
        return _sanitize_id(userdomain)

    joined = _net_get_join_id(timeout_s=2.0)
    if joined:
        return joined

    if userdomain:
        return _sanitize_id(userdomain)
    return "workgroup"


def domain_channel(domain: str | None = None) -> str:
    return f"#{domain_or_workgroup_id(domain)}"


def _net_get_join_id(timeout_s: float = 2.0) -> str | None:
    """Best-effort NetGetJoinInformation (domain or workgroup name)."""
    if os.name != "nt":
        return None
    box: dict[str, str | None] = {"name": None}

    def worker() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            netapi = ctypes.WinDLL("netapi32")
            NetGetJoinInformation = netapi.NetGetJoinInformation
            NetGetJoinInformation.argtypes = [
                wintypes.LPCWSTR,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(ctypes.c_int),
            ]
            NetGetJoinInformation.restype = wintypes.DWORD
            NetApiBufferFree = netapi.NetApiBufferFree
            NetApiBufferFree.argtypes = [wintypes.LPVOID]
            NetApiBufferFree.restype = wintypes.DWORD

            buf = wintypes.LPWSTR()
            join_type = ctypes.c_int()
            # NetSetupUnknownStatus=0, Workgroup=1, Domain=3 (values vary by SDK;
            # we only need the name string).
            rc = NetGetJoinInformation(None, ctypes.byref(buf), ctypes.byref(join_type))
            if rc == 0 and buf.value:
                box["name"] = str(buf.value)
            if buf:
                NetApiBufferFree(buf)
        except Exception:
            return

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if box["name"]:
        return _sanitize_id(box["name"])
    return None


def parse_chanserv_info(text: str, channel: str) -> ShopProbeResult:
    """Classify a ChanServ INFO NOTICE for ``channel``.

    Returns ``registered``, ``missing``, or ``unknown`` (keep waiting / treat as
    missing after probe timeout).
    """
    body = (text or "").strip()
    if not body:
        return "unknown"
    t = body.lower()
    ch = (channel or "").lower().lstrip("#")
    if any(
        s in t
        for s in (
            "is not registered",
            "isn't registered",
            "isnt registered",
            "not registered",
        )
    ):
        return "missing"
    if "no such channel" in t and ch and ch in t.replace("#", ""):
        return "missing"
    # Atheme / Ergo-style success. Ergo: "Channel #foo is registered" (no colon).
    if "registered:" in t or "registered on" in t or "registered at" in t:
        return "registered"
    if "is registered" in t:
        return "registered"
    if "information on" in t and ch and ch in t.replace("#", ""):
        return "registered"
    if "founder:" in t and ch and ch in t.replace("#", ""):
        return "registered"
    return "unknown"


def is_channel_target(target: str) -> bool:
    t = (target or "").strip()
    return bool(t) and t[0] in "#&+"


def nick_matches_pattern(pattern: str, nick: str, machine: str | None = None) -> bool:
    """True if IRC/client ping pattern matches this console (#298).

    Examples: ``*``, ``flam*``, ``flamingo_console``, ``flamingo``, ``flamingo_1``.
    """
    pat = (pattern or "").strip()
    if not pat or pat == "*":
        return True
    n = (nick or "").strip().lower()
    mid = machine_id(machine)
    candidates = {
        n,
        mid,
        f"console-{mid}",
        f"{mid}_console",
        machine_console_nick(mid),
        domain_lobby_nick(mid),
        f"#{mid}",
    }
    p = pat.lower()
    # Allow #channel-style patterns too.
    for c in candidates:
        if not c:
            continue
        if fnmatch.fnmatchcase(c, p) or fnmatch.fnmatchcase(c.lstrip("#"), p.lstrip("#")):
            return True
        # Prefix match without wildcard: "flam" matches flamingo / flamingo_console
        if "*" not in p and "?" not in p and (c.startswith(p) or c.lstrip("#").startswith(p)):
            return True
    return False


def parse_ctcp_ping(text: str) -> str | None:
    """Return CTCP PING payload (possibly empty string) or None if not CTCP PING."""
    m = _CTCP_PING_RE.match(text or "")
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else ""


def parse_ping_command(text: str) -> str | None:
    """Return ping pattern (``*`` if bare ``ping``) or None if not a ping command."""
    m = _PING_CMD_RE.match(text or "")
    if not m:
        return None
    return (m.group(1) or "*").strip()


def is_bob_fleet_nick(nick: str) -> bool:
    """True for fleet ear nicks ``bob-{machinename}`` (issue #302)."""
    return bool(_BOB_FLEET_NICK_RE.match((nick or "").strip()))


@dataclass
class AuthPolicy:
    """Only authenticated operators may drive the console via PRIVMSG."""

    operators: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    account_map: AccountMap | None = None
    require_account: bool = False
    # When set, also allow bob-<machine> for this box; bob-* fleet nicks always allowed (#302).
    machine: str | None = None

    def allow(self, nick: str, account: str | None = None) -> bool:
        n = (nick or "").strip().lower()
        if not n:
            return False
        # Fleet bob-{machine} seats are already authenticated on Ergo (#302).
        if is_bob_fleet_nick(n):
            return True
        ops = {x.lower() for x in self.operators}
        mid = machine_id(self.machine) if self.machine is not None else None
        if mid:
            ops.add(f"bob-{mid}")
        accts = {x.lower() for x in self.accounts}
        if self.account_map is not None and account is None:
            account = self.account_map.get(n)
        acct = (account or "").strip().lower()
        need_acct = self.require_account or bool(accts)
        if need_acct:
            if not acct or acct == "*":
                return False
            if accts and acct not in accts:
                return False
        if ops:
            return n in ops
        return need_acct


@dataclass(frozen=True)
class ConsoleCapabilities:
    """FR #3287: install-time remote capability gates (survive MSI upgrade).

    ``shell_mode``: ``off`` = STATUS/ping only; ``operators`` = FR #75 shell for auth nicks.
    ``jobs`` / ``update``: finer gates when shell is ``operators``.
    """

    shell_mode: Literal["off", "operators"] = "operators"
    jobs: Literal["off", "on"] = "on"
    update: Literal["on", "off"] = "on"
    require_account: bool = False
    accounts: tuple[str, ...] = ()

    def log_line(self) -> str:
        return (
            f"INFO capabilities shell={self.shell_mode} jobs={self.jobs} "
            f"update={self.update} require_account={int(bool(self.require_account))} "
            f"accounts={len(self.accounts)}"
        )


def normalize_shell_cli(value: str | None) -> tuple[str | None, str | None]:
    """Return ``(shell_mode, powershell_path)`` for a ``--shell`` CLI token.

    FR #3287: exact ``off`` / ``operators`` are capability modes; any other value
    remains the PowerShell executable path (legacy ``--shell``).
    """
    raw = (value or "").strip()
    if not raw:
        return None, None
    low = raw.lower()
    if low in SHELL_MODE_TOKENS:
        return low, None
    return None, raw


def _norm_on_off(value: str | None, *, default: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {"on", "off"}:
        return raw
    return default


def resolve_shell_mode_for_install(
    *,
    prior_shell: str | None,
    explicit: str | None,
    had_prior_service: bool,
) -> str:
    """Fresh MSI default ``off``; upgrade of an existing fleet box defaults ``operators``."""
    exp = (explicit or "").strip().lower()
    if exp in SHELL_MODE_TOKENS:
        return exp
    prior = (prior_shell or "").strip().lower()
    if prior in SHELL_MODE_TOKENS:
        return prior
    return "operators" if had_prior_service else "off"


def load_capabilities(
    *,
    install_root: Path | str | None = None,
    console_home: Path | str | None = None,
    cli_shell: str | None = None,
    cli_shell_mode: str | None = None,
    cli_jobs: str | None = None,
    cli_update: str | None = None,
    cli_require_account: bool | None = None,
    cli_accounts: list[str] | tuple[str, ...] | None = None,
    default_shell_mode: str = "operators",
) -> ConsoleCapabilities:
    """Merge CLI + ``config\\airc.json`` (install root, then console home)."""
    data: dict = {}
    roots: list[Path] = []
    if install_root:
        roots.append(Path(install_root))
    if console_home:
        roots.append(Path(console_home))
    for root in roots:
        for rel in ("config/airc.json", "airc.json"):
            path = root / rel
            if not path.is_file():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if isinstance(raw, dict):
                data.update(raw)
                break

    mode_cli, _path = normalize_shell_cli(cli_shell)
    mode = (cli_shell_mode or mode_cli or data.get("shell") or data.get("shell_mode") or default_shell_mode)
    mode = str(mode).strip().lower()
    if mode not in SHELL_MODE_TOKENS:
        mode = default_shell_mode

    jobs = _norm_on_off(cli_jobs if cli_jobs is not None else data.get("jobs"), default="on")
    update = _norm_on_off(
        cli_update if cli_update is not None else data.get("update"), default="on"
    )

    req = cli_require_account
    if req is None:
        req = bool(data.get("require_account"))
    accts: list[str] = []
    if cli_accounts:
        accts.extend(str(x).strip() for x in cli_accounts if str(x).strip())
    cfg_accts = data.get("accounts")
    if isinstance(cfg_accts, str):
        accts.extend(x.strip() for x in re.split(r"[,;\s]+", cfg_accts) if x.strip())
    elif isinstance(cfg_accts, (list, tuple)):
        accts.extend(str(x).strip() for x in cfg_accts if str(x).strip())
    # dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for a in accts:
        k = a.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)

    return ConsoleCapabilities(
        shell_mode=mode,  # type: ignore[arg-type]
        jobs=jobs,  # type: ignore[arg-type]
        update=update,  # type: ignore[arg-type]
        require_account=bool(req),
        accounts=tuple(uniq),
    )


def _read_airc_json_dict(install_root: Path | str | None) -> dict:
    """Load ``config\\airc.json`` (or ``airc.json``) from an install root."""
    if not install_root:
        return {}
    root = Path(install_root)
    for rel in ("config/airc.json", "airc.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            return raw
    return {}


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class AircStartUpdatePolicy:
    """FR #3289: whether service start may git-sync ``main`` or run signed MSI self-update.

    Fresh MSI default: ``sync_from_repo=False`` (unsigned main must not run as SYSTEM).
    ``self_update`` defaults True (sha256-checked release MSI path); lock workstations set it false.
    """

    sync_from_repo: bool = False
    self_update: bool = True

    def log_lines(self) -> tuple[str, ...]:
        return (
            f"INFO sync-from-repo={'on' if self.sync_from_repo else 'off'} (config)",
            f"INFO self-update={'on' if self.self_update else 'off'} (config)",
        )


def load_start_update_policy(
    install_root: Path | str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> AircStartUpdatePolicy:
    """Merge env + ``config\\airc.json`` into start-hook policy (FR #3289).

    Precedence:
    - ``BOBIVERSE_NO_UPDATE=1`` → both off
    - ``BOBIVERSE_SYNC_FROM_REPO=0|1`` / ``BOBIVERSE_SELF_UPDATE=0|1`` when set
    - ``BOB_AUTOUPDATE=0`` → self_update off (updater also honours this)
    - ``airc.json`` ``sync_from_repo`` / ``self_update``
    - defaults: sync off, self_update on
    """
    e = env if env is not None else os.environ
    if (e.get("BOBIVERSE_NO_UPDATE") or "").strip() == "1":
        return AircStartUpdatePolicy(sync_from_repo=False, self_update=False)

    data = _read_airc_json_dict(install_root)
    sync = _coerce_bool(data.get("sync_from_repo"), default=False)
    self_upd = _coerce_bool(data.get("self_update"), default=True)

    sync_env = (e.get("BOBIVERSE_SYNC_FROM_REPO") or "").strip()
    if sync_env != "":
        sync = _coerce_bool(sync_env, default=sync)
    self_env = (e.get("BOBIVERSE_SELF_UPDATE") or "").strip()
    if self_env != "":
        self_upd = _coerce_bool(self_env, default=self_upd)
    if (e.get("BOB_AUTOUPDATE") or "").strip() == "0":
        self_upd = False

    return AircStartUpdatePolicy(sync_from_repo=sync, self_update=self_upd)


def resolve_sync_from_repo_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
) -> bool:
    """Fresh / omitted → False; explicit MSI/CLI wins; else keep prior (FR #3289)."""
    if explicit is not None:
        return bool(explicit)
    if prior is not None:
        return bool(prior)
    return False


def resolve_self_update_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
) -> bool:
    """Fresh / omitted → True; explicit wins; else keep prior (FR #3289)."""
    if explicit is not None:
        return bool(explicit)
    if prior is not None:
        return bool(prior)
    return True


@dataclass
class ConsoleSession:
    nick: str
    proc: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_at: float = field(default_factory=time.time)

    def write_line(self, text: str) -> None:
        self.last_at = time.time()
        if self.proc.stdin is None:
            raise RuntimeError("console stdin closed")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.alive():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


class ConsoleSessionManager:
    """One interactive shell per authenticated nick."""

    def __init__(
        self,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
        idle_sec: float = 3600.0,
    ) -> None:
        self.shell = shell or DEFAULT_SHELL
        self.cwd = cwd
        self.on_output = on_output
        self.idle_sec = idle_sec
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}

    def get_or_create(self, nick: str) -> ConsoleSession:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.get(key)
            if sess and sess.alive():
                sess.last_at = time.time()
                return sess
            if sess:
                sess.close()
            proc = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )
            sess = ConsoleSession(nick=key, proc=proc)
            self._sessions[key] = sess
            if self.on_output and proc.stdout is not None:
                threading.Thread(
                    target=self._pump,
                    args=(key, proc),
                    name=f"airc-console-{key}",
                    daemon=True,
                ).start()
            return sess

    def _pump(self, nick: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                text = line.rstrip("\r\n")
                if self.on_output:
                    self.on_output(nick, text)
        except Exception:
            pass

    def pipe(self, nick: str, command: str) -> ConsoleSession:
        sess = self.get_or_create(nick)
        sess.write_line(command)
        return sess

    def close_nick(self, nick: str) -> None:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.pop(key, None)
        if sess:
            sess.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
        for _, sess in items:
            sess.close()

    def reap_idle(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead: list[str] = []
        with self._lock:
            for k, sess in list(self._sessions.items()):
                if (not sess.alive()) or (now - sess.last_at > self.idle_sec):
                    dead.append(k)
            for k in dead:
                sess = self._sessions.pop(k, None)
                if sess:
                    sess.close()
        return len(dead)

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())


@dataclass
class HandleResult:
    action: str
    nick: str | None = None
    target: str | None = None
    text: str | None = None
    reply: str | None = None


class ShellRequestError(ValueError):
    """Malformed or oversized console shell request (FR #75)."""


ShellKind = Literal["ps", "cmd", "psb64"]


@dataclass
class ShellRequest:
    kind: ShellKind
    body: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ShellOutcome:
    job_id: str
    exit_code: int
    stdout: str
    stderr: str


def resolve_powershell() -> str:
    """Windows PowerShell 5.1 host (not pwsh) unless AIRC_POWERSHELL overrides."""
    env = (os.environ.get("AIRC_POWERSHELL") or "").strip()
    if env:
        return env
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    return found or "powershell.exe"


def resolve_comspec() -> str:
    return (os.environ.get("COMSPEC") or "").strip() or "cmd.exe"


# FR #2580: redirected powershell.exe defaults $OutputEncoding to ASCII, which
# best-fits non-ASCII (α→a, CJK→?) before airc UTF-8-decodes stdout (U+FFFD).
# FR #2641: also silence progress records — redirected hosts otherwise emit
# ``#< CLIXML`` / ``Preparing modules for first use`` on stderr (extra IRC flood
# and a non-empty StdErr for ExitCode 0 callers).
# FR #2910: keep each preamble statement on its own line so terminating errors
# do not fuse ``$ProgressPreference`` / ``UTF8Encoding`` into the user statement
# (char offsets / preamble leak). FR #2918: PowerShell still numbers those
# preamble lines, so ``plain_text_powershell_stderr`` rewrites ``At line:N`` by
# subtracting ``ps_utf8_preamble_line_count()`` to match the user script.
PS_UTF8_STDOUT_PREAMBLE = (
    "$ProgressPreference = 'SilentlyContinue'\n"
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false\n"
    "$OutputEncoding = [Console]::OutputEncoding\n"
)

_CLIXML_ERROR_S_RE = re.compile(
    r'<S\s+S="Error">(.*?)</S>',
    re.IGNORECASE | re.DOTALL,
)
_CLIXML_HEX_ESC_RE = re.compile(r"_x([0-9A-Fa-f]{4})_", re.IGNORECASE)
_AT_LINE_RE = re.compile(r"At line:(\d+)(\s+char:)", re.IGNORECASE)


def ps_utf8_preamble_line_count() -> int:
    """How many script lines ``PS_UTF8_STDOUT_PREAMBLE`` occupies before user text (FR #2918)."""
    p = PS_UTF8_STDOUT_PREAMBLE or ""
    if not p:
        return 0
    if p.endswith("\n"):
        return p.count("\n")
    return p.count("\n") + 1


def wrap_ps_script_utf8_stdout(script: str) -> str:
    """Prefix a PowerShell script for UTF-8 stdout + silent progress (FR #2580 / #2641 / #2910)."""
    return PS_UTF8_STDOUT_PREAMBLE + (script or "")


def _unescape_powershell_clixml_text(text: str) -> str:
    """Decode PowerShell CLIXML ``_xHHHH_`` escapes (CR/LF and friends)."""

    def _one(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 16))
        except ValueError:
            return m.group(0)

    return _CLIXML_HEX_ESC_RE.sub(_one, text or "")


def _adjust_at_line_numbers(text: str, offset: int) -> str:
    """Rewrite ``At line:N`` to user-script coordinates (FR #2918)."""
    if offset <= 0 or not text:
        return text

    def _repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return f"At line:{max(1, n - offset)}{m.group(2)}"

    return _AT_LINE_RE.sub(_repl, text)


def plain_text_powershell_stderr(
    stderr: str, *, at_line_offset: int | None = None
) -> str:
    """Turn redirected PowerShell CLIXML stderr into plain error text (FR #2910 / #2918).

    Windows PowerShell 5.1 serialises the error stream as ``#< CLIXML`` / ``<Objs>``
    when stdout/stderr are redirected. Extract ``<S S=\"Error\">`` payloads, unescape
    ``_xHHHH_``, drop progress/noise records, and strip residual wrapper preamble
    echoes so IRC ``err`` lines carry the real message only.

    Default ``at_line_offset`` is ``ps_utf8_preamble_line_count()`` so ``At line:``
    matches the operator script (pass ``0`` for raw CLIXML fixtures that were not
    wrapped).
    """
    raw = stderr or ""
    if not raw:
        return ""
    if at_line_offset is None:
        at_line_offset = ps_utf8_preamble_line_count()
    looks_clixml = ("#< CLIXML" in raw) or ("<Objs" in raw and 'S="Error"' in raw)
    if looks_clixml:
        parts = [
            _unescape_powershell_clixml_text(m.group(1)).strip("\r\n")
            for m in _CLIXML_ERROR_S_RE.finditer(raw)
        ]
        # Drop empty / whitespace-only Error nodes.
        parts = [p for p in parts if p.strip()]
        plain = "\n".join(parts).strip()
        if not plain:
            # Fallback: strip CLIXML chrome rather than returning empty.
            plain = re.sub(r"(?is)#<\s*CLIXML\s*", "", raw)
            plain = re.sub(r"(?is)</?Objs[^>]*>", "", plain)
            plain = _unescape_powershell_clixml_text(plain).strip()
    else:
        plain = raw
    # Never leak the UTF-8 / progress wrapper into operator-visible StdErr.
    drop_markers = (
        "ProgressPreference",
        "UTF8Encoding",
        "$OutputEncoding",
        "[Console]::OutputEncoding",
    )
    kept: list[str] = []
    for line in plain.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if any(m in line for m in drop_markers):
            # Keep lines that also carry the real error after a fused preamble.
            # e.g. "... OutputEncoding; Write-Error 'boom' : boom"
            if ":" in line and any(
                tok in line for tok in ("Write-Error", "Cannot find", "Exception", "Error")
            ):
                # Prefer text after the last preamble marker when fused.
                cut = line
                for m in drop_markers:
                    if m in cut:
                        idx = cut.rfind(m)
                        # advance past ';' if present after the marker span
                        semi = cut.find(";", idx)
                        if semi != -1:
                            cut = cut[semi + 1 :].lstrip()
                if cut and cut != line:
                    kept.append(cut)
                    continue
            continue
        kept.append(line)
    plain = "\n".join(kept).strip()
    return _adjust_at_line_numbers(plain, int(at_line_offset or 0))


def encode_ps_encoded_command(script: str) -> str:
    """Base64 of UTF-16LE script text for ``powershell -EncodedCommand``.

    Always wraps with UTF-8 OutputEncoding (FR #2580) and silent progress (FR #2641).
    """
    wrapped = wrap_ps_script_utf8_stdout(script)
    return base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")


def _looks_like_utf16le_script(raw: bytes) -> bool:
    """True when bytes look like UTF-16LE (ASCII-heavy scripts have 0x00 on odd indexes)."""
    if len(raw) < 2 or len(raw) % 2:
        return False
    zeros = sum(1 for i in range(1, len(raw), 2) if raw[i] == 0)
    return zeros >= max(1, len(raw) // 4)


def prepare_psb64_encoded_command(payload: str) -> str:
    """Decode ``psb64:`` payload to an ``-EncodedCommand`` ASCII base64 string.

    Rules (FR #75): decode UTF-16LE or UTF-8 script text, then always re-encode
    via ``encode_ps_encoded_command`` so the FR #2580 UTF-8 stdout wrap applies
    (do not return raw payload bytes without the wrap).
    """
    text = (payload or "").strip()
    if not text:
        raise ShellRequestError("malformed psb64: empty")
    if len(text) > PSB64_MAX_CHARS:
        raise ShellRequestError("psb64 too large")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error as exc:
        raise ShellRequestError("malformed psb64") from exc
    if _looks_like_utf16le_script(raw):
        try:
            # Re-encode via encode_ps_encoded_command so FR #2580 UTF-8 wrap applies.
            return encode_ps_encoded_command(raw.decode("utf-16-le"))
        except UnicodeDecodeError:
            pass
    try:
        script = raw.decode("utf-8")
        return encode_ps_encoded_command(script)
    except UnicodeDecodeError:
        pass
    if len(raw) % 2 == 0:
        try:
            return encode_ps_encoded_command(raw.decode("utf-16-le"))
        except UnicodeDecodeError as exc:
            raise ShellRequestError("malformed psb64") from exc
    raise ShellRequestError("malformed psb64")


_HEARD_PAYLOAD_RE = re.compile(r"(?is)\bHeard:\s*(.+)$")
_BOBTALK_PREFIX_RE = re.compile(
    r"(?is)^@\S+\s+\S+\s+here\.\s*(?:weekly=[^.]+\.)?\s*"
)


def sanitize_console_operator_text(text: str) -> str:
    """Strip Halloy/bobtalk nick-prefix and ``Heard:`` wrappers (FR #2570).

    Live failure: clients relay ``@marchhare_console marchhare here. weekly=27. Heard: STATUS …``
    into the console PRIVMSG; PowerShell then sees ``@marchhare_console`` as a splat.
    Prefer the payload after ``Heard:``; otherwise strip a bobtalk ``@nick mid here.`` prefix
    when the remainder looks like a console command / FR #78 verb.

    FR #2570 follow-up: bobtalk-only presence lines (no command after the prefix) return
    empty so ``handle_raw`` drops them — never pipe ``@nick`` / ``weekly=N`` into PowerShell.
    MRB #2573: do not treat PowerShell ``@(…)`` / ``@'`` / ``@"`` as nick-mentions; drop only
    ``@token`` nick-like lines. Remove unreachable duplicate sanitize tail.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    m = _HEARD_PAYLOAD_RE.search(raw)
    if m:
        return (m.group(1) or "").strip()
    m2 = _BOBTALK_PREFIX_RE.match(raw)
    if m2:
        rest = raw[m2.end() :].strip()
        # Presence-only: "@nick mid here. weekly=26." or leftover "weekly=26"
        if not rest or re.fullmatch(r"(?i)weekly=\S+", rest):
            return ""
        return rest
    # Nick-mention splat (not PowerShell array/here-string @( @' @" ).
    if raw.startswith("@") and len(raw) > 1 and raw[1] not in "('\"":
        return ""
    return raw


def parse_shell_request(text: str) -> ShellRequest:
    """Parse a console PRIVMSG into ps / cmd: / psb64: (FR #75).

    Optional leading ``id=<8 hex>`` (FR #1546) pins the DONE/out/err correlation id
    so Invoke-AircRemote can wait on ``airc-replies.jsonl``.
    """
    raw = sanitize_console_operator_text(text or "")
    if not raw:
        raise ShellRequestError("empty command")
    job_id: str | None = None
    m = re.match(r"(?is)^id=([0-9a-f]{8})\s+(.*)$", raw)
    if m:
        job_id = m.group(1).lower()
        raw = m.group(2).strip()
        if not raw:
            raise ShellRequestError("empty command after id=")
    low = raw.lower()
    if low.startswith("psb64:"):
        payload = raw[6:]
        # Validate early; body stores original payload for argv build.
        prepare_psb64_encoded_command(payload)
        req = ShellRequest(kind="psb64", body=payload)
    elif low.startswith("cmd:"):
        body = raw[4:].lstrip()
        if not body:
            raise ShellRequestError("empty cmd:")
        req = ShellRequest(kind="cmd", body=body)
    else:
        req = ShellRequest(kind="ps", body=raw)
    if job_id:
        req.job_id = job_id
    return req


def build_shell_argv(req: ShellRequest) -> list[str]:
    if req.kind == "cmd":
        # FR #2580: OEM code page mangles non-ASCII; force UTF-8 CP for capture.
        body = req.body or ""
        stripped = body.lstrip().lower()
        if not stripped.startswith("chcp "):
            body = "chcp 65001>nul & " + body
        return [resolve_comspec(), "/d", "/c", body]
    if req.kind == "psb64":
        enc = prepare_psb64_encoded_command(req.body)
    else:
        enc = encode_ps_encoded_command(req.body)
    return [
        resolve_powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        enc,
    ]


def _clip_bytes(data: bytes, limit: int = SHELL_OUTPUT_MAX_BYTES) -> tuple[str, bool]:
    clipped = len(data) > limit
    chunk = data[:limit]
    return chunk.decode("utf-8", errors="replace"), clipped


def run_shell_request(
    req: ShellRequest,
    *,
    timeout_s: float = SHELL_TIMEOUT_S,
    cwd: str | None = None,
) -> ShellOutcome:
    argv = build_shell_argv(req)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out, _ = _clip_bytes(exc.stdout or b"")
        err, _ = _clip_bytes(exc.stderr or b"")
        err = plain_text_powershell_stderr(err)
        err = (err + ("\n" if err else "") + f"timeout after {timeout_s:.0f}s").strip()
        return ShellOutcome(job_id=req.job_id, exit_code=124, stdout=out, stderr=err)
    out, out_clip = _clip_bytes(proc.stdout or b"")
    err, err_clip = _clip_bytes(proc.stderr or b"")
    # FR #2910: PowerShell 5.1 error stream is CLIXML under redirect — plain-text it.
    err = plain_text_powershell_stderr(err)
    if out_clip:
        out += "\n[clipped stdout]"
    if err_clip:
        err += "\n[clipped stderr]"
    return ShellOutcome(
        job_id=req.job_id,
        exit_code=int(proc.returncode),
        stdout=out,
        stderr=err,
    )


def chunk_irc_text(text: str, *, limit: int = IRC_SAFE_PAYLOAD, prefix: str = "") -> list[str]:
    """Split ``text`` so each ``prefix + chunk`` fits ``limit`` (IRC-safe)."""
    room = max(8, limit - len(prefix))
    raw = text.replace("\r", "").replace("\n", " ")
    if not raw:
        return [prefix] if prefix else [""]
    return [prefix + raw[i : i + room] for i in range(0, len(raw), room)]


def format_shell_replies(
    outcome: ShellOutcome,
    *,
    irc_limit: int = IRC_SAFE_PAYLOAD,
) -> list[str]:
    """Stable output contract: ordered out/err seq lines + terminal DONE (FR #75)."""
    lines: list[str] = []
    seq = 0

    def emit(stream: str, label: str) -> None:
        nonlocal seq
        parts = stream.splitlines() if stream else []
        if stream and not parts:
            parts = [""]
        for part in parts:
            # Reserve prefix room using a provisional seq width, then emit.
            body = part
            while True:
                seq += 1
                prefix = f"{label} id={outcome.job_id} seq={seq} "
                room = max(8, irc_limit - len(prefix))
                piece, body = body[:room], body[room:]
                lines.append(prefix + piece)
                if not body:
                    break

    emit(outcome.stdout, "out")
    emit(outcome.stderr, "err")
    lines.append(f"DONE id={outcome.job_id} exit={outcome.exit_code}")
    return lines


@dataclass
class _ShellPending:
    """One queued shell command (FR #2632); ``done`` signals completion for wait=True."""

    command: str
    done: threading.Event = field(default_factory=threading.Event)


class ShellJobRunner:
    """Run FR #75 shell requests; emit reply lines to the operator Query.

    FR #2632: one in-flight shell per Query nick plus a short pending queue so
    concurrent Invoke-AircRemote Commands both get a real DONE. Overflow still
    fail-closes with busy DONE (FR #2612: no hang / no lost DONE).
    """

    def __init__(
        self,
        *,
        on_reply: Callable[[str, str], None] | None = None,
        cwd: str | None = None,
        timeout_s: float = SHELL_TIMEOUT_S,
        wait: bool = False,
        on_inflight: Callable[[str, str], None] | None = None,
        on_idle: Callable[[str], None] | None = None,
        pending_max: int = SHELL_PENDING_MAX,
    ) -> None:
        self.on_reply = on_reply
        self.cwd = cwd
        self.timeout_s = timeout_s
        self.wait = wait
        self.on_inflight = on_inflight
        self.on_idle = on_idle
        self.pending_max = max(0, int(pending_max))
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._pending: dict[str, deque[_ShellPending]] = {}
        self._inflight_cmd: dict[str, _ShellPending] = {}

    def start(self, nick: str, command: str) -> str:
        key = nick.strip().lower()
        item = _ShellPending(command=command)

        with self._lock:
            q = self._pending.setdefault(key, deque())
            prev = self._threads.get(key)
            busy = prev is not None and prev.is_alive()
            # When a shell is live, at most pending_max more may wait; overflow fail-closes.
            if busy and len(q) >= self.pending_max:
                overflow = True
            else:
                overflow = False
                q.append(item)
                if not busy:
                    t = threading.Thread(
                        target=self._drain, args=(key,), name=f"airc-shell-{key}", daemon=True
                    )
                    self._threads[key] = t
                    t.start()

        if overflow:
            # FR #2612 / #2632: queue full — fail closed with DONE (Wait must not hang).
            try:
                req = parse_shell_request(command)
                jid = req.job_id
            except ShellRequestError as exc:
                jid = uuid.uuid4().hex[:8]
                self._emit(key, f"err id={jid} seq=1 {exc}")
                self._emit(key, f"DONE id={jid} exit=2")
                return key
            self._emit(key, f"err id={jid} seq=1 busy: prior shell still emitting")
            self._emit(key, f"DONE id={jid} exit=1")
            return key

        if self.wait:
            item.done.wait(timeout=self.timeout_s + 5)
        return key

    def _drain(self, key: str) -> None:
        while True:
            with self._lock:
                q = self._pending.get(key)
                if not q:
                    self._pending.pop(key, None)
                    self._threads.pop(key, None)
                    self._inflight_cmd.pop(key, None)
                    return
                item = q.popleft()
                self._inflight_cmd[key] = item
            try:
                self._run_one(key, item.command)
            finally:
                item.done.set()
                with self._lock:
                    if self._inflight_cmd.get(key) is item:
                        self._inflight_cmd.pop(key, None)
                if self.on_idle:
                    try:
                        self.on_idle(key)
                    except Exception:
                        pass

    def _run_one(self, key: str, command: str) -> None:
        jid: str | None = None
        try:
            try:
                req = parse_shell_request(command)
            except ShellRequestError as exc:
                jid = uuid.uuid4().hex[:8]
                self._emit(key, f"err id={jid} seq=1 {exc}")
                self._emit(key, f"DONE id={jid} exit=2")
                return
            jid = req.job_id
            if self.on_inflight:
                try:
                    self.on_inflight(key, jid)
                except Exception:
                    pass
            outcome = run_shell_request(req, timeout_s=self.timeout_s, cwd=self.cwd)
            for line in format_shell_replies(outcome):
                self._emit(key, line)
        except Exception:
            # Keep drain alive for queued peers; always emit DONE when we have an id.
            if jid:
                self._emit(key, f"err id={jid} seq=1 shell runner fault")
                self._emit(key, f"DONE id={jid} exit=1")

    def _emit(self, nick: str, line: str) -> None:
        # FR #2551: on_reply may raise ConnectionError after IRC drop; swallow so the
        # worker thread does not die with an unhandled exception (crash hook).
        if self.on_reply:
            try:
                self.on_reply(nick, line)
            except ConnectionError:
                return

    def open_job_ids(self) -> list[tuple[str, str]]:
        """(nick, job_id) for in-flight + pending commands (FR #2640 stop flush)."""
        out: list[tuple[str, str]] = []
        with self._lock:
            for key, item in list(self._inflight_cmd.items()):
                try:
                    jid = parse_shell_request(item.command).job_id
                except ShellRequestError:
                    jid = uuid.uuid4().hex[:8]
                out.append((key, jid))
            for key, q in list(self._pending.items()):
                for item in list(q):
                    if self._inflight_cmd.get(key) is item:
                        continue
                    try:
                        jid = parse_shell_request(item.command).job_id
                    except ShellRequestError:
                        jid = uuid.uuid4().hex[:8]
                    out.append((key, jid))
        return out

    def abandon_open_jobs(self) -> list[tuple[str, str]]:
        """Drop pending/in-flight bookkeeping and unblock waiters; return job ids (FR #2640)."""
        ids = self.open_job_ids()
        with self._lock:
            pending_all = list(self._pending.items())
            self._pending.clear()
            self._inflight_cmd.clear()
        for _key, q in pending_all:
            for item in q:
                item.done.set()
        return ids

    def close_nick(self, nick: str) -> None:
        # Oneshoot threads are daemon; drop tracking + pending for this Query.
        key = nick.strip().lower()
        with self._lock:
            self._threads.pop(key, None)
            pending = self._pending.pop(key, None)
            self._inflight_cmd.pop(key, None)
        if pending:
            for item in pending:
                item.done.set()


@dataclass
class ConsoleSession:
    nick: str
    proc: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_at: float = field(default_factory=time.time)

    def write_line(self, text: str) -> None:
        self.last_at = time.time()
        if self.proc.stdin is None:
            raise RuntimeError("console stdin closed")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.alive():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


class ConsoleSessionManager:
    """One interactive shell per authenticated nick."""

    def __init__(
        self,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
        idle_sec: float = 3600.0,
    ) -> None:
        self.shell = shell or DEFAULT_SHELL
        self.cwd = cwd
        self.on_output = on_output
        self.idle_sec = idle_sec
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}

    def get_or_create(self, nick: str) -> ConsoleSession:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.get(key)
            if sess and sess.alive():
                sess.last_at = time.time()
                return sess
            if sess:
                sess.close()
            proc = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )
            sess = ConsoleSession(nick=key, proc=proc)
            self._sessions[key] = sess
            if self.on_output and proc.stdout is not None:
                threading.Thread(
                    target=self._pump,
                    args=(key, proc),
                    name=f"airc-console-{key}",
                    daemon=True,
                ).start()
            return sess

    def _pump(self, nick: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                text = line.rstrip("\r\n")
                if self.on_output:
                    self.on_output(nick, text)
        except Exception:
            pass

    def pipe(self, nick: str, command: str) -> ConsoleSession:
        sess = self.get_or_create(nick)
        sess.write_line(command)
        return sess

    def close_nick(self, nick: str) -> None:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.pop(key, None)
        if sess:
            sess.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
        for _, sess in items:
            sess.close()

    def reap_idle(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead: list[str] = []
        with self._lock:
            for k, sess in list(self._sessions.items()):
                if (not sess.alive()) or (now - sess.last_at > self.idle_sec):
                    dead.append(k)
            for k in dead:
                sess = self._sessions.pop(k, None)
                if sess:
                    sess.close()
        return len(dead)

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())


@dataclass
class HandleResult:
    action: str
    nick: str | None = None
    target: str | None = None
    text: str | None = None
    reply: str | None = None




class AircConsoleCore:
    """Pure handler: parse PRIVMSG, gate auth, pipe to console, stay silent on channel."""

    def __init__(
        self,
        *,
        machine: str | None = None,
        auth: AuthPolicy,
        sessions: ConsoleSessionManager | None = None,
        nick: str = NICK,
        shell_runner: ShellJobRunner | None = None,
        update_scheduler: Callable[..., UpdateScheduleResult] | None = None,
        install_root: str | None = None,
        job_protocol: JobProtocol | None = None,
        capabilities: ConsoleCapabilities | None = None,
    ) -> None:
        self.machine = machine_id(machine)
        self.channel = shop_channel(self.machine)
        self.auth = auth
        self.nick = nick
        self.sessions = sessions or ConsoleSessionManager()
        self.shell_runner = shell_runner
        self.channel_traffic: list[str] = []
        self.update_scheduler = update_scheduler or schedule_fleet_update
        self.install_root = install_root
        self.job_protocol = job_protocol
        # Default operators preserves pre-#3287 unit tests / hotpatched fleets without airc.json.
        self.capabilities = capabilities or ConsoleCapabilities()

    def register_commands(self) -> list[str]:
        """NickServ register / identify sequence (password from env/file at service layer)."""
        return [
            f"NICK {self.nick}",
            f"USER {self.nick} 0 * :airc console service",
        ]

    def join_commands(self) -> list[str]:
        # Ergo creates channel on first JOIN when permitted; silent — no PRIVMSG.
        return [f"JOIN {self.channel}"]

    def may_speak_on_channel(self) -> bool:
        return False

    def handle_raw(self, line: str) -> HandleResult | None:
        tags, rest = parse_message_tags(line.rstrip("\r\n"))
        m = _PRIVMSG_RE.match(rest)
        if not m:
            return None
        nick, target, text = m.group(1), m.group(2), m.group(3)
        account = tags.get("account")
        if self.auth.account_map is not None and account:
            self.auth.account_map.set(nick, account)

        # Issue #298: CTCP PING / "ping [pattern]" — no operator auth; presence only.
        ctcp_payload = parse_ctcp_ping(text or "")
        if ctcp_payload is not None:
            return HandleResult(
                action="ctcp_pong",
                nick=nick,
                target=target,
                text=text,
                reply=ctcp_payload,
            )
        ping_pat = parse_ping_command(text or "")
        if ping_pat is not None:
            if nick_matches_pattern(ping_pat, self.nick, self.machine):
                return HandleResult(
                    action="pong",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"pong {self.nick}",
                )
            if is_channel_target(target):
                self.channel_traffic.append(text)
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            # Direct ping that does not match us — ignore quietly.
            return HandleResult(action="ping_miss", nick=nick, target=target, text=text)

        if is_channel_target(target):
            # Silent in channel: ignore public traffic (do not reply on channel).
            self.channel_traffic.append(text)
            return HandleResult(action="silent_channel", nick=nick, target=target, text=text)

        # Direct PRIVMSG to console nick
        if not self.auth.allow(nick, account):
            return HandleResult(
                action="deny",
                nick=nick,
                target=target,
                text=text,
                reply="denied: authenticate / not an operator",
            )

        # FR #2570: strip Halloy/bobtalk Heard:/@nick noise before verb/shell routing.
        cmd = sanitize_console_operator_text(text or "")
        if not cmd:
            return HandleResult(action="empty", nick=nick, target=target, text=text)
        if cmd.lower() in {".quit", "!quit", "exit"}:
            self.sessions.close_nick(nick)
            return HandleResult(action="close", nick=nick, target=target, text=text, reply="console closed")
        if cmd.lower() in {".help", "!help"}:
            return HandleResult(
                action="help",
                nick=nick,
                target=target,
                text=text,
                reply=(
                    "airc console (FR #75/#3287): default PowerShell -NoProfile; "
                    "cmd: COMSPEC escape; psb64:<base64> EncodedCommand; "
                    "replies out/err id= seq= then DONE id= exit=; "
                    "STATUS|PUT|CHUNK|PUTEND|RUN|GET|JOB|CANCEL; "
                    "UPDATE airc|bob|jeeves [ver] schedules detached MSI update; "
                    f"capabilities shell={self.capabilities.shell_mode} "
                    f"jobs={self.capabilities.jobs} update={self.capabilities.update}; "
                    ".quit closes; silent on channel; answers ping"
                ),
            )

        caps = self.capabilities

        # FR #77: UPDATE schedules Update-BobiverseService Check (detached); never msiexec here.
        parsed = parse_update_command(cmd)
        if parsed is not None:
            # FR #3287: shell=off is status-only; update=off refuses even when shell=operators.
            if caps.shell_mode == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            if caps.update == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 update-disabled",
                )
            product, ver = parsed
            try:
                result = self.update_scheduler(
                    product,
                    version=ver,
                    install_root=self.install_root,
                )
            except TypeError:
                # test doubles may omit kwargs
                result = self.update_scheduler(product, version=ver)
            if not isinstance(result, UpdateScheduleResult):
                result = UpdateScheduleResult(
                    False, "bad-scheduler", product=product, version=ver
                )
            return HandleResult(
                action="update",
                nick=nick,
                target=target,
                text=text,
                reply=result.reply_line(),
            )

        # FR #78: PUT/RUN/JOB/STATUS protocol (before plain shell).
        parsed = parse_job_verb(cmd)
        if parsed is not None and self.job_protocol is not None:
            verb, kv = parsed
            # FR #3287: shell=off keeps STATUS only; jobs=off refuses write/exec verbs.
            if caps.shell_mode == "off" and verb != "STATUS":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            if caps.jobs == "off" and verb != "STATUS":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 jobs-disabled",
                )
            self.job_protocol.handle_async(nick, verb, kv)
            return HandleResult(action="job", nick=nick, target=target, text=text)

        # FR #75: oneshot PowerShell / cmd: / psb64: with DONE framing.
        if self.shell_runner is not None:
            if caps.shell_mode == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            self.shell_runner.start(nick, cmd)
            return HandleResult(action="shell", nick=nick, target=target, text=text)

        # Legacy interactive pipe (tests / AIRC without runner).
        if caps.shell_mode == "off":
            return HandleResult(
                action="capability_deny",
                nick=nick,
                target=target,
                text=text,
                reply="DONE exit=126 shell-disabled",
            )
        self.sessions.pipe(nick, cmd)
        return HandleResult(action="pipe", nick=nick, target=target, text=text)


def load_operators(path: Path | None, cli: list[str] | None = None) -> set[str]:
    ops: set[str] = set()
    if cli:
        ops.update(x.strip().lstrip("\ufeff") for x in cli if x and x.strip())
    if path and path.is_file():
        # utf-8-sig strips BOM from PowerShell Set-Content -Encoding utf8 (issue #289).
        text = path.read_text(encoding="utf-8-sig")
        for line in text.splitlines():
            s = line.strip().lstrip("\ufeff")
            if not s or s.startswith("#"):
                continue
            ops.add(s)
    return ops


def home_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("AIRC_CONSOLE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".airc-console"


def ensure_nickserv_password(path: Path, *, mint: bool = True) -> str | None:
    """Load or mint the NickServ password (issue #271).

    First start writes a GUID into ``console.password`` and reuses it later.
    This is **not** the Ergo server PASS — that comes from env / ergo.password.
    """
    import uuid

    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    if not mint:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = str(uuid.uuid4())
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        # Best-effort: owner-only on POSIX; Windows ACLs set by install/hotpatch.
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def resolve_server_password(
    *,
    home: Path | None = None,
    password_file: Path | None = None,
) -> str | None:
    """Ergo / IRC server PASS — never invent; never use NickServ GUID file alone.

    Order: AIRC_CONSOLE_SERVER_PASSWORD, AGENTIC_IRC_PASSWORD, AIRC_CONSOLE_PASSWORD
    (legacy), then ``ergo.password`` / ``connect.password`` beside home or
    ``~/.grok/ergo/connect.password``. Explicit ``password_file`` is **not** used
    here when it is the NickServ GUID path (``console.password``).
    """
    for key in (
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_PASSWORD",
    ):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    candidates: list[Path] = []
    # Legacy: only treat password_file as server PASS when it is NOT console.password
    if password_file is not None and password_file.name.lower() != "console.password":
        candidates.append(password_file)
    if home is not None:
        candidates.extend(
            [
                home / "ergo.password",
                home / "connect.password",
            ]
        )
    # Fleet default connect.password — only when using the real user console home
    # (avoid leaking ~/.grok secrets into hermetic tests with a tmp home).
    real_home = home_dir()
    if home is None or Path(home).resolve() == real_home.resolve():
        candidates.append(Path.home() / ".grok" / "ergo" / "connect.password")
    for p in candidates:
        try:
            if p.is_file():
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None
