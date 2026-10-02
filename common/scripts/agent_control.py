"""File-based graceful QUIT for irc_agent (Windows has no SIGTERM to hidden python)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import protect

QUIT_REQUEST = "agent.quit.request"


def quit_request_path(home: Path | str) -> Path:
    return Path(home).expanduser() / QUIT_REQUEST


def request_agent_quit(home: Path | str, reason: str = "stop") -> None:
    path = quit_request_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (reason or "stop").strip().replace("\n", " ")[:200]
    path.write_text(f"{int(time.time())} {text}\n", encoding="utf-8")
    try:
        protect.protect_path(path)
    except protect.ProtectError:
        pass


def peek_quit_request(home: Path | str) -> str | None:
    path = quit_request_path(home)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    parts = raw.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else "stop"


def consume_quit_request(home: Path | str) -> str | None:
    reason = peek_quit_request(home)
    if reason is None:
        return None
    try:
        quit_request_path(home).unlink(missing_ok=True)
    except OSError:
        pass
    return reason


def _home_in_cmdline(home: Path, cmdline: str) -> bool:
    h = str(home)
    return h in cmdline or h.replace("\\", "/") in cmdline


def find_irc_agent_pid(home: Path | str) -> int | None:
    home_p = Path(home).expanduser().resolve()
    if os.name != "nt":
        return _find_irc_agent_pid_posix(home_p)
    return _find_irc_agent_pid_win(home_p)


def _find_irc_agent_pid_posix(home_p: Path) -> int | None:
    import subprocess

    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        if "irc_agent.py" not in line:
            continue
        if _home_in_cmdline(home_p, line):
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


def _find_irc_agent_pid_win(home_p: Path) -> int | None:
    import subprocess

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
        return None
    import json

    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    esc = str(home_p)
    for row in rows or []:
        cmd = str(row.get("CommandLine") or "")
        if "irc_agent.py" not in cmd:
            continue
        if esc in cmd or esc.replace("\\", "\\\\") in cmd:
            try:
                return int(row.get("ProcessId"))
            except (TypeError, ValueError):
                continue
    return None


def wait_agent_exit(home: Path | str, timeout_s: float) -> bool:
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        if find_irc_agent_pid(home) is None:
            return True
        time.sleep(0.2)
    return find_irc_agent_pid(home) is None


def graceful_stop_agent(home: Path | str, reason: str = "stop", wait_s: float = 12.0) -> bool:
    """Request QUIT via control file; wait for irc_agent process to exit."""
    pid = find_irc_agent_pid(home)
    if pid is None:
        return True
    request_agent_quit(home, reason)
    return wait_agent_exit(home, wait_s)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Request graceful irc_agent QUIT")
    p.add_argument("--home", required=True)
    p.add_argument("--reason", default="stop")
    p.add_argument("--wait-s", type=float, default=12.0)
    p.add_argument("--request-only", action="store_true")
    args = p.parse_args(argv)
    if args.request_only:
        request_agent_quit(args.home, args.reason)
        return 0
    ok = graceful_stop_agent(args.home, args.reason, args.wait_s)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
