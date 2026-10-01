"""Jeeves !recycle {machine} and RECYCLE v1 wire (issue #152)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import bobreport

RECYCLE_WIRE_PREFIX = "RECYCLE v1 "
CHAIR_ENV = "BOB_CHAIR_MACHINE"


def chair_home_machine() -> str:
    """Machine the chair (Jeeves) runs on: BOB_CHAIR_MACHINE, else this host name (#42).

    Was hardcoded ``ionos``; the box is ``win-mpre8vi4u6u`` now and ids come from ChanServ."""
    raw = (os.environ.get(CHAIR_ENV) or os.environ.get("COMPUTERNAME") or "").strip().lower()
    if not raw:
        import socket

        raw = socket.gethostname().strip().lower()
    return bobreport.normalize_machine_id(raw) or raw
# FR #197 (gh-Jeeves): RECYCLE machine=<id> by=<nick> scope=local|fleet exec=local-bob-seat
_JEEVES_ROUTE_RE = re.compile(
    r"^RECYCLE\s+machine=(\S+)\s+by=\S+\s+scope=(\S+)\s+exec=local-bob-seat\s*$",
    re.I,
)


def format_recycle_wire(machine_id: str) -> str:
    mid = (machine_id or "").strip().lower()
    return f"{RECYCLE_WIRE_PREFIX}{mid}"


def parse_jeeves_recycle_route(body: str) -> tuple[str, str] | None:
    """Parse FR #197 shop wire. Returns ``(machine_id, scope)`` or None."""
    text = (body or "").strip()
    m = _JEEVES_ROUTE_RE.match(text)
    if not m:
        return None
    raw_mid = (m.group(1) or "").strip().lower()
    scope = (m.group(2) or "local").strip().lower()
    if raw_mid in ("bobiverse", "agentic_irc", "unknown", ""):
        raw_mid = chair_home_machine()
    if raw_mid == "fleet" or scope == "fleet":
        return "fleet", "fleet"
    if raw_mid == "dev1":
        raw_mid = "ce-priority-dev1"
    mid = resolve_recycle_machine(raw_mid)
    if not mid:
        return None
    return mid, scope


def parse_recycle_wire(body: str) -> str | None:
    """Accept legacy ``RECYCLE v1 <machine>`` or FR #197 ``RECYCLE machine=…``."""
    text = (body or "").strip()
    jeeves = parse_jeeves_recycle_route(text)
    if jeeves:
        mid, scope = jeeves
        if scope == "fleet" or mid == "fleet":
            # Caller must expand fleet to local machine id.
            return "fleet"
        return mid
    if not text.lower().startswith(RECYCLE_WIRE_PREFIX.lower()):
        return None
    token = text[len(RECYCLE_WIRE_PREFIX) :].strip().split(None, 1)[0]
    return resolve_recycle_machine(token)


def resolve_recycle_machine(token: str) -> str | None:
    raw = (token or "").strip().lower()
    if raw in {"jeeves", "ircjeeves"}:
        return "jeeves"
    mid = bobreport.normalize_machine_id(token)
    if not mid:
        return None
    if mid not in bobreport.roster_machine_ids() and mid != chair_home_machine():
        return None
    return mid


def parse_recycle_query(body: str) -> tuple[str, str | None] | None:
    """Return (kind, machine_id). kind is 'run' or 'refuse'. None if not !recycle."""
    text = (body or "").strip()
    if not text:
        return None
    parts = text.split()
    if parts[0].lower() != "!recycle":
        return None
    if len(parts) < 2:
        return ("refuse", None)
    mid = resolve_recycle_machine(parts[1])
    if not mid:
        return ("refuse", parts[1].lower())
    return ("run", mid)


def local_fleet_machine_id() -> str | None:
    raw = (os.environ.get("BOB_MACHINE_ID") or os.environ.get("COMPUTERNAME") or "").strip().lower()
    if not raw:
        return None
    return resolve_recycle_machine(raw) or bobreport.normalize_machine_id(raw)


def chair_targets_local(machine_id: str) -> bool:
    return machine_id == chair_home_machine()


def find_install_root() -> Path | None:
    here = Path(__file__).resolve().parent
    if (here / "irc_agent.py").is_file():
        return here.parent
    return None


def _native_abspath(path: Path | str) -> str:
    """Absolute path string without pathlib.resolve() (POSIX-safe when os.name is faked)."""
    return os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path))))


def find_agentic_build_root() -> Path | None:
    for candidate in (
        Path(os.environ.get("BOB_REPO_ROOT", "")).expanduser(),
        Path(r"C:\ai\agentic_build"),
        Path(r"D:\ai\agentic_build"),
    ):
        if not str(candidate):
            continue
        tray = candidate / "tools" / "Watch-BobTray.ps1"
        if tray.is_file():
            return candidate
    return None


@dataclass
class RecyclePlan:
    machine_id: str
    ionos_chair: bool
    steps: list[str] = field(default_factory=list)


def build_recycle_plan(machine_id: str, *, ionos_chair: bool) -> RecyclePlan:
    steps = ["git_pull_install", "restart_watch_bobiverse", "recycle_watch_bobtray"]
    if ionos_chair and machine_id == chair_home_machine():
        steps.extend(["restart_bob_chair", "restart_bobcallback"])
    return RecyclePlan(machine_id=machine_id, ionos_chair=ionos_chair, steps=steps)


@dataclass
class RecycleHooks:
    git_pull: Callable[[Path], None] | None = None
    restart_watch: Callable[[Path, str], None] | None = None
    recycle_tray: Callable[[Path], None] | None = None
    restart_chair: Callable[[Path, Path], None] | None = None
    restart_callback: Callable[[Path, Path], None] | None = None


def _default_git_pull(repo: Path) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "pull", "--ff-only"],
        check=False,
        capture_output=True,
        text=True,
    )


def _win_process_commandlines(match_substr: str) -> list[tuple[int, str]]:
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    import json

    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(rows, dict):
        rows = [rows]
    hits: list[tuple[int, str]] = []
    for row in rows or []:
        cmd = str(row.get("CommandLine") or "")
        if match_substr.lower() in cmd.lower():
            try:
                hits.append((int(row.get("ProcessId")), cmd))
            except (TypeError, ValueError):
                continue
    return hits


def _win_kill_matching_ps1(script_name: str) -> list[int]:
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$n='{script_name}'; Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -and $_.CommandLine -match $n } | "
                "Select-Object ProcessId | ConvertTo-Json -Compress",
            ],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    import json

    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(rows, dict):
        rows = [rows] if rows.get("ProcessId") else []
    killed: list[int] = []
    for row in rows or []:
        try:
            pid = int(row.get("ProcessId"))
        except (TypeError, ValueError):
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
            killed.append(pid)
        except OSError:
            pass
    return killed


def _stop_bobiverse_moot(build_root: Path, machine_id: str) -> None:
    """Match Watch-BobTray Stop-BobiverseMoot. Do not stop BobFleet-* / Watch-BobJobs."""
    if os.name != "nt":
        return
    task = f"_Watch-Bobiverse-{machine_id}"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Stop-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    _win_kill_matching_ps1("Watch-Bobiverse.ps1")
    _win_kill_matching_ps1("_Watch-Bobiverse")
    for pid, cmd in _win_process_commandlines("irc_agent.py"):
        low = cmd.lower()
        if "bobiverse" not in low:
            continue
        if "--chair" in low:
            continue
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)


def _start_bobiverse_moot_wrapper(build_root: Path, machine_id: str) -> None:
    """Match Start-BobiverseMootWrapper: scheduled task XOR wrapper, not both."""
    if os.name != "nt":
        return
    task = f"_Watch-Bobiverse-{machine_id}"
    started = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-ScheduledTask -TaskName '{task}' -ErrorAction Stop",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode == 0:
        return
    wrap = build_root / "tools" / f"_Watch-Bobiverse-{machine_id}.ps1"
    generic = build_root / "tools" / "_Watch-Bobiverse.ps1"
    watch = build_root / "tools" / "Watch-Bobiverse.ps1"
    script = wrap if wrap.is_file() else generic if generic.is_file() else watch
    if not script.is_file():
        return
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(build_root),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def _default_restart_watch(build_root: Path, machine_id: str) -> None:
    _stop_bobiverse_moot(build_root, machine_id)
    _start_bobiverse_moot_wrapper(build_root, machine_id)


def _default_recycle_tray(build_root: Path) -> None:
    """Restart TipForm via the same bootstrap as tray Restart (agentic_build#442).

    Prefer ``Start-BobFleetTray.ps1 -ForceNew`` over a raw Watch-BobTray.ps1
    launch so git update / seat wrapper / tidy stay on one path.
    """
    if os.name != "nt":
        return
    start = build_root / "tools" / "Start-BobFleetTray.ps1"
    tray = build_root / "tools" / "Watch-BobTray.ps1"
    if start.is_file():
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-STA",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(start),
                "-RepoRoot",
                str(build_root),
                "-ForceNew",
            ],
            cwd=str(build_root),
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0,
        )
        return
    # Fallback when Start-BobFleetTray is missing (tests / sparse trees).
    _win_kill_matching_ps1("Watch-BobTray.ps1")
    if not tray.is_file():
        return
    time.sleep(0.3)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-STA",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tray),
        ],
        cwd=str(build_root),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def digest_home_native() -> str:
    """digest.json / chair-outbox.txt root. Not the Jeeves identity home.

    Use os.path, not pathlib.Path: tests fake os.name as ``nt`` and WindowsPath
    cannot be constructed on this host.
    """
    env = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if env:
        return _native_abspath(env)
    profile = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
    if not profile:
        profile = os.path.expanduser("~")
    return _native_abspath(os.path.join(profile, ".bobiverse"))


def _default_restart_chair(irc_root: Path, home: Path) -> None:
    """Detach chair + bobcallback restart. Do not wait in this process."""
    if os.name != "nt":
        return
    scripts = irc_root / "scripts"
    install = scripts / "Install-BobChair.ps1"
    callback = scripts / "bobcallback.py"
    home_s = _native_abspath(home)
    digest_s = digest_home_native()
    helper_path = os.path.join(home_s, "recycle-chair-after-exit.ps1")

    def _ps_sq(s: Path | str) -> str:
        return "'" + os.fspath(s).replace("'", "''") + "'"

    helper_body = "\n".join(
        [
            f"$waitPid = {os.getpid()}",
            f"$install = {_ps_sq(install)}",
            f"$callback = {_ps_sq(callback)}",
            f"$agentHome = {_ps_sq(home_s)}",
            f"$digestHome = {_ps_sq(digest_s)}",
            f"$scripts = {_ps_sq(scripts)}",
            "while (Get-Process -Id $waitPid -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 1 }",
            "if (Test-Path -LiteralPath $install) {",
            "  Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$install) -WorkingDirectory $scripts -WindowStyle Hidden | Out-Null",
            "}",
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {",
            "  $_.CommandLine -and $_.CommandLine -match 'bobcallback\\.py'",
            "} | ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue }",
            "if (Test-Path -LiteralPath $callback) {",
            "  Start-Process -FilePath python -ArgumentList @('-u',$callback,'--home',$digestHome) -WorkingDirectory $scripts -WindowStyle Hidden | Out-Null",
            "}",
            "",
        ]
    )
    with open(helper_path, "w", encoding="utf-8") as fh:
        fh.write(helper_body)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            helper_path,
        ],
        cwd=str(scripts),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def _restart_bobcallback_task() -> bool:
    """#53: the jeeves installer registers the ``BobCallback`` scheduled task; prefer it.

    End + Run the task so the receiver comes back under the same supervisor/args the MSI
    configured. Returns False (caller falls back to a direct spawn) when the task is absent.
    """
    if os.name != "nt":
        return False
    try:
        q = subprocess.run(["schtasks", "/Query", "/TN", "BobCallback"], capture_output=True, text=True)
        if q.returncode != 0:
            return False
        subprocess.run(["schtasks", "/End", "/TN", "BobCallback"], capture_output=True, text=True)
        for pid, _cmd in _win_process_commandlines("bobcallback.py"):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
        r = subprocess.run(["schtasks", "/Run", "/TN", "BobCallback"], capture_output=True, text=True)
        return r.returncode == 0
    except OSError:
        return False


def _default_restart_callback(_home: Path, irc_root: Path) -> None:
    """Restart bobcallback on the digest home. `_home` is the Jeeves identity home."""
    if os.name != "nt":
        return
    digest_s = digest_home_native()
    if _restart_bobcallback_task():
        return
    for pid, _cmd in _win_process_commandlines("bobcallback.py"):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
    cb = irc_root / "scripts" / "bobcallback.py"
    if not cb.is_file():
        return
    subprocess.Popen(
        [sys.executable or "python", "-u", str(cb), "--home", digest_s],
        cwd=str(irc_root / "scripts"),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def execute_local_recycle(
    machine_id: str,
    home: Path | str,
    *,
    ionos_chair: bool = False,
    hooks: RecycleHooks | None = None,
) -> RecyclePlan:
    """Run recycle on this box. Returns the plan that was executed."""
    mid = resolve_recycle_machine(machine_id) or machine_id
    plan = build_recycle_plan(mid, ionos_chair=ionos_chair)
    h = hooks or RecycleHooks()
    irc_root = find_install_root()
    build_root = find_agentic_build_root()
    if h.git_pull:
        h.git_pull(irc_root or Path("."))
    elif irc_root:
        _default_git_pull(irc_root)
    if h.restart_watch:
        h.restart_watch(build_root or Path("."), mid)
    elif build_root:
        _default_restart_watch(build_root, mid)
    if h.recycle_tray:
        h.recycle_tray(build_root or Path("."))
    elif build_root:
        _default_recycle_tray(build_root)
    if ionos_chair and mid == chair_home_machine() and (h.restart_chair or irc_root):
        (h.restart_chair or _default_restart_chair)(irc_root, Path(home))
        if h.restart_callback:
            h.restart_callback(Path(home), irc_root)
    return plan


def refuse_message(token: str | None) -> str:
    if token:
        return f"recycle: refused unknown machine {token}"
    return "recycle: need a registered machine name (see ChanServ shops)"


def ack_message(machine_id: str, *, local: bool) -> str:
    disp = bobreport.SHORT_TO_MACHINE.get(machine_id, machine_id)
    if machine_id == "ce-priority-dev1":
        disp = "dev1"
    if local:
        return f"recycle: started {disp} on this box"
    return f"recycle: requested {disp}"


def restarting_announce(machine_id: str, nick: str) -> str:
    """Channel line before host ops — Bob must say this, then actually recycle."""
    disp = bobreport.SHORT_TO_MACHINE.get(machine_id, machine_id)
    if machine_id == "ce-priority-dev1":
        disp = "dev1"
    who = (nick or "bob").strip() or "bob"
    # ASCII hyphen (PS 5.1 / logs). agentic_build#442: announce then tray via Start-BobFleetTray.
    return (
        f"{who}: recycling {disp} - logging off IRC then restarting "
        f"Watch-Bobiverse + TipForm tray (deterministic)"
    )
