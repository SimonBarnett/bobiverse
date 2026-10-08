# -*- coding: utf-8 -*-
"""FR #3181: 2-worker cap counts only IRC-joined bob-worker *agent* seats.

Plan / maintenance / monitor never register. Agent seats write a marker after
JOIN #<machine> and remove it on PART/QUIT/irc-lost/exit. Cap readers count
only markers whose pid is still alive.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Optional

SEATS_SUBDIR = ("Bobiverse", "worker", "run", "seats")


def localappdata() -> Path:
    la = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(la)


def seats_dir(root: Optional[Path | str] = None) -> Path:
    if root is not None:
        return Path(root)
    return localappdata().joinpath(*SEATS_SUBDIR)


def seat_path(nick: str, root: Optional[Path | str] = None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (nick or "").strip()) or "unknown"
    return seats_dir(root) / f"{safe}.irc.json"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SYNCHRONIZE = 0x00100000
        h = k32.OpenProcess(SYNCHRONIZE, 0, int(pid))
        if h:
            k32.CloseHandle(h)
            return True
        # OpenProcess can fail for access denied on live processes — fall back to Toolhelp.
        return _pid_in_toolhelp(int(pid))
    except Exception:
        return False


def _pid_in_toolhelp(pid: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        class PE(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)
        if not snap or snap == wintypes.HANDLE(-1).value:
            return False
        try:
            e = PE()
            e.dwSize = ctypes.sizeof(PE)
            ok = k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                if int(e.th32ProcessID) == pid:
                    return True
                ok = k32.Process32NextW(snap, ctypes.byref(e))
        finally:
            k32.CloseHandle(snap)
        return False
    except Exception:
        return False


def write_seat_irc(
    *,
    nick: str,
    pid: int,
    machine: str,
    shop: str = "",
    root: Optional[Path | str] = None,
    now: Optional[float] = None,
) -> Path:
    """Register an IRC-joined agent seat. Idempotent overwrite for the nick."""
    d = seats_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = seat_path(nick, d)
    body = {
        "v": 1,
        "nick": nick,
        "pid": int(pid),
        "machine": (machine or "").strip().lower(),
        "shop": shop or (f"#{machine}" if machine else ""),
        "joined_at": float(time.time() if now is None else now),
        "mode": "agent",
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def clear_seat_irc(
    nick: Optional[str] = None,
    *,
    pid: Optional[int] = None,
    root: Optional[Path | str] = None,
) -> int:
    """Remove seat markers by nick and/or pid. Returns number of files removed."""
    d = seats_dir(root)
    if not d.is_dir():
        return 0
    removed = 0
    for p in list(d.glob("*.irc.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
            continue
        match_nick = nick is not None and str(data.get("nick", "")).lower() == str(nick).lower()
        match_pid = pid is not None and int(data.get("pid") or 0) == int(pid)
        if (nick is None and pid is None) or match_nick or match_pid:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def list_live_irc_agent_seats(
    root: Optional[Path | str] = None,
    *,
    machine: Optional[str] = None,
    pid_alive_fn=None,
) -> list[dict[str, Any]]:
    """Return marker payloads for live agent seats (stale pid files are deleted)."""
    d = seats_dir(root)
    if not d.is_dir():
        return []
    alive = pid_alive_fn or pid_alive
    mid = (machine or "").strip().lower()
    out: list[dict[str, Any]] = []
    for p in list(d.glob("*.irc.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        if str(data.get("mode") or "agent").lower() != "agent":
            continue
        if mid and str(data.get("machine") or "").lower() != mid:
            continue
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if not alive(pid):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        out.append(data)
    return out


def count_irc_agent_seats(
    root: Optional[Path | str] = None,
    *,
    machine: Optional[str] = None,
    exclude_pid: Optional[int] = None,
    pid_alive_fn=None,
) -> int:
    seats = list_live_irc_agent_seats(root, machine=machine, pid_alive_fn=pid_alive_fn)
    if exclude_pid is None:
        return len(seats)
    ex = int(exclude_pid)
    return sum(1 for s in seats if int(s.get("pid") or 0) != ex)


HARD_MAX_WORKERS = 2


def worker_cap_refusal_irc(
    *,
    for_mode: str = "agent",
    root: Optional[Path | str] = None,
    machine: Optional[str] = None,
    my_pid: Optional[int] = None,
    max_workers: int = HARD_MAX_WORKERS,
    pid_alive_fn=None,
) -> str:
    """'' = free to start. Plan/monitor/maintenance never refused. Cap = IRC-joined agents only."""
    if str(for_mode).lower() != "agent":
        return ""
    n = count_irc_agent_seats(
        root,
        machine=machine,
        exclude_pid=my_pid,
        pid_alive_fn=pid_alive_fn,
    )
    cap = max(0, int(max_workers))
    if n >= cap:
        return (
            "max %d workers (%d IRC-joined agent seats on this machine) - not starting another"
            % (HARD_MAX_WORKERS, n)
        )
    return ""
