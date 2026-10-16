# -*- coding: utf-8 -*-
"""FR #3181 / FR #4307: 2-worker cap for bob-worker *agent* seats.

Plan / maintenance / monitor never register. Agent seats write a marker after
JOIN #<machine> and remove it on PART/QUIT/irc-lost/exit.

FR #4307: markers alone undercount when an older build or tray restart leaves
``run\\seats`` empty while agent processes are still live. Cap readers count the
union of (a) markers whose pid is still alive and (b) live agent bob-worker
seat roots from the process snapshot. Stale markers (dead pid) never count.

FR #4458: a onefile seat writes the child pid into the marker while the process
scan counts the bootloader root. Those two pids are one seat. A marker pid that
walks up to a live agent root is not a second seat. A marker whose pid is not
in that tree still counts (the FR #4307 disjoint case).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

SEATS_SUBDIR = ("Bobiverse", "worker", "run", "seats")
_WORKER_EXE_RX = re.compile(r"^bob-worker(?:-[0-9a-f]+)?\.exe$", re.I)


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


def _entry_mode(entry) -> str:
    """Optional 4th tuple field: mode name or full cmdline. Missing => unknown (not agent)."""
    if not isinstance(entry, (tuple, list)) or len(entry) < 4:
        return "unknown"
    raw = str(entry[3] or "").strip().lower()
    if raw in ("agent", "plan", "monitor", "maintenance"):
        return raw
    m = re.search(r"--mode[=\s]+(agent|plan|monitor|maintenance)", raw)
    return m.group(1) if m else "unknown"


def live_agent_root_pids(procs: Optional[Iterable] = None) -> set[int]:
    """Root bob-worker*.exe PIDs whose mode is explicitly agent (FR #3181 / #4307)."""
    rows: dict[int, tuple[int, str, str]] = {}
    for entry in procs or []:
        try:
            p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        except (TypeError, ValueError, IndexError):
            continue
        rows[p] = (pp, n, _entry_mode(entry))
    workers = {p for p, (_pp, n, _m) in rows.items() if _WORKER_EXE_RX.match(n)}
    roots = {p for p in workers if rows[p][0] not in workers}
    return {p for p in roots if rows[p][2] == "agent"}


def _proc_rows(procs: Optional[Iterable]) -> dict[int, tuple[int, str, str]]:
    rows: dict[int, tuple[int, str, str]] = {}
    for entry in procs or []:
        try:
            p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        except (TypeError, ValueError, IndexError):
            continue
        rows[p] = (pp, n, _entry_mode(entry))
    return rows


def marker_pid_under_agent_root(pid: int, rows: dict, roots: set[int]) -> bool:
    """FR #4458: True when ``pid`` is an agent root or a descendant of one."""
    seen: set[int] = set()
    cur = int(pid)
    while cur and cur not in seen:
        seen.add(cur)
        if cur in roots:
            return True
        row = rows.get(cur)
        if row is None:
            return False
        cur = int(row[0])
    return False


def count_cap_agent_seats(
    root: Optional[Path | str] = None,
    *,
    machine: Optional[str] = None,
    exclude_pid: Optional[int] = None,
    pid_alive_fn=None,
    procs: Optional[Iterable] = None,
) -> int:
    """FR #4307 / FR #4458: live agent roots, plus marker pids not already in those trees."""
    rows = _proc_rows(procs) if procs is not None else {}
    roots = live_agent_root_pids(procs) if procs is not None else set()
    identities: set[int] = set(roots)
    for s in list_live_irc_agent_seats(root, machine=machine, pid_alive_fn=pid_alive_fn):
        try:
            pid = int(s.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0:
            continue
        if procs is not None and marker_pid_under_agent_root(pid, rows, roots):
            continue
        identities.add(pid)
    if exclude_pid is not None:
        ex = int(exclude_pid)
        identities.discard(ex)
        if procs is not None and marker_pid_under_agent_root(ex, rows, roots):
            cur = ex
            seen: set[int] = set()
            while cur and cur not in seen:
                seen.add(cur)
                if cur in roots:
                    identities.discard(cur)
                    break
                row = rows.get(cur)
                if row is None:
                    break
                cur = int(row[0])
    return len(identities)


def count_irc_agent_seats(
    root: Optional[Path | str] = None,
    *,
    machine: Optional[str] = None,
    exclude_pid: Optional[int] = None,
    pid_alive_fn=None,
    procs: Optional[Iterable] = None,
) -> int:
    """Back-compat name for the FR #4307 cap count (markers ∪ live agent roots)."""
    return count_cap_agent_seats(
        root,
        machine=machine,
        exclude_pid=exclude_pid,
        pid_alive_fn=pid_alive_fn,
        procs=procs,
    )


HARD_MAX_WORKERS = 2


def worker_cap_refusal_irc(
    *,
    for_mode: str = "agent",
    root: Optional[Path | str] = None,
    machine: Optional[str] = None,
    my_pid: Optional[int] = None,
    max_workers: int = HARD_MAX_WORKERS,
    pid_alive_fn=None,
    procs: Optional[Iterable] = None,
) -> str:
    """'' = free to start. Plan/monitor/maintenance never refused.

    Cap = live agent roots plus IRC markers that are not the child of one of those roots (FR #4307 / FR #4458).
    """
    if str(for_mode).lower() != "agent":
        return ""
    n = count_cap_agent_seats(
        root,
        machine=machine,
        exclude_pid=my_pid,
        pid_alive_fn=pid_alive_fn,
        procs=procs,
    )
    cap = max(0, int(max_workers))
    if n >= cap:
        return (
            "max %d workers (%d agent seats on this machine) - not starting another"
            % (HARD_MAX_WORKERS, n)
        )
    return ""
