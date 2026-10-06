"""Remote worker start over IRC (t810u): ``!startworker [agent|plan] [machine]``.

The Bob ear (service, session 0, LocalSystem) can not open a window on the user's desktop. The tray
(Watch-BobTray.ps1) is the one process that already lives in the interactive session and already owns the
"Agent" click (Start-BobTrayWorkerExe), so the ear only *authorises, caps and queues*; the tray *launches*:

  ear   : authenticate (verified services account) -> machine check -> kill-switch -> tray alive? (= somebody is
          logged in with the tray up) -> worker cap -> cooldown -> write ``req-<id>.json`` -> reply ACK / NACK
  tray  : host/ThreadPool writes ``tray.alive`` every ~2 s (FR #2697: not on the WinForms poll thread);
          consumes ``req-*.json`` on a UI tick (deleted BEFORE launch: at-most-once, expired after
          REQUEST_TTL_S) -> Start-BobTrayWorkerExe -> ``res-<id>.json`` (audit only)

No credentials cross this queue, only {id, mode, by, ts}. Everything here is pure / injectable so it is testable
without IRC, a desktop or Windows.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

CMD = "!startworker"
MODES = ("agent", "plan")
DEFAULT_MODE = "agent"
HARD_MAX_WORKERS = 2             # t815u / FR #2522: ONLY mode=agent seats; plan is uncapped and does not count
DEFAULT_MAX_WORKERS = HARD_MAX_WORKERS
DEFAULT_COOLDOWN_S = 30.0        # between two accepted starts on one machine
REQUEST_TTL_S = 60.0             # a queued request older than this is dropped by the tray
TRAY_ALIVE_MAX_AGE_S = 30.0      # tray heartbeat freshness (host/ThreadPool writes every ~2 s; FR #2697: ≥2× worst UI refresh stall)
QUEUE_SUBDIR = ("run", "startworker")
ALIVE_FILE = "tray.alive"
DISABLE_FILE = "startworker.disabled"
WORKER_EXE_RE = re.compile(r"^bob-worker(?:-[0-9a-f]+)?\.exe$", re.I)
_MACHINE_RE = re.compile(r"^#?[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
_JUNK = {c: None for c in range(0, 32)}


def parse(body: str):
    """``!startworker [agent|plan] [machine]`` (either order). -> (mode, machine|None) | 'usage' | None (not ours)."""
    text = str(body or "").translate(_JUNK).strip().lstrip(":").strip()
    if not text:
        return None
    parts = text.split()
    if parts[0].lower() != CMD:
        return None
    mode, machine = None, None
    for tok in parts[1:]:
        low = tok.lower()
        if low in MODES:
            if mode is not None:
                return "usage"
            mode = low
        elif machine is None and _MACHINE_RE.match(tok):
            machine = low.lstrip("#")
        else:
            return "usage"
    return (mode or DEFAULT_MODE, machine)


def usage() -> str:
    return "usage: !startworker [agent|plan] [machine]   (machine required in #bobiverse)"


# --------------------------------------------------------------------------- who may ask

def owner_accounts() -> set:
    out = {(os.environ.get("JEEVES_OWNER_ACCOUNT") or "simon").strip().lower() or "simon"}
    extra = (os.environ.get("BOB_OP_ACCOUNTS") or "")
    out |= {p.strip().lower() for p in extra.split(",") if p.strip()}
    return out


def authorize(nick: str, account, *, machine_of_nick: Callable[[str], str | None],
              chair_nicks: Iterable[str] = ("jeeves",), owners: set | None = None):
    """-> (ok, kind, reason). Only a VERIFIED services account counts; a nick alone proves nothing.

    owner : account in the owner set (Simon), any nick
    ear   : nick bob-<machine> logged in to the account of the same name (Bob ears)
    chair : nick == account in the chair nicks (Jeeves)
    """
    n = str(nick or "").strip()
    low = n.lower()
    acct = str(account or "").strip().lower()
    if not acct:
        return False, "", "unverified"
    if acct in (owners if owners is not None else owner_accounts()):
        return True, "owner", ""
    same = acct in (low, low.rstrip("_"))
    if same and low in {c.lower() for c in chair_nicks}:
        return True, "chair", ""
    if same and low.startswith("bob-") and machine_of_nick(n):
        return True, "ear", ""
    return False, "", "denied"


# --------------------------------------------------------------------------- workers on this machine

def _entry_mode(entry) -> str:
    if not isinstance(entry, (tuple, list)) or len(entry) < 4:
        return "agent"
    raw = str(entry[3] or "").strip().lower()
    if raw in ("agent", "plan", "monitor", "maintenance"):
        return raw
    import re as _re
    m = _re.search(r"--mode[=\s]+(agent|plan|monitor|maintenance)", raw)
    return m.group(1) if m else "agent"


def count_workers(procs: Iterable[tuple], *, modes: tuple = ("agent",)) -> int:
    """Root bob-worker*.exe seats whose mode is in ``modes`` (default: agent/worker only).

    FR #2522: plan/maintenance never count toward the IRC ``!startworker`` cap. Optional 4th
    tuple field is mode or cmdline; missing mode defaults to agent.
    """
    rows = []
    for entry in procs:
        p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        rows.append((p, pp, n, _entry_mode(entry)))
    wk = {p for p, _pp, n, _m in rows if WORKER_EXE_RE.match(n)}
    wanted = {str(m).lower() for m in modes}
    return sum(1 for p, pp, n, m in rows if p in wk and pp not in wk and m in wanted)


def snapshot_procs() -> list:
    """(pid, ppid, name) for every process (Toolhelp32; [] off Windows)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((int(e.th32ProcessID), int(e.th32ParentProcessID), str(e.szExeFile)))
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


# --------------------------------------------------------------------------- queue (ear side)

def queue_dir(install_root) -> Path:
    return Path(install_root).joinpath(*QUEUE_SUBDIR)


def tray_alive(qdir, now: float | None = None, max_age: float = TRAY_ALIVE_MAX_AGE_S) -> bool:
    now = time.time() if now is None else now
    try:
        return 0.0 <= now - (Path(qdir) / ALIVE_FILE).stat().st_mtime <= max_age
    except OSError:
        return False


def write_request(qdir, mode: str, by: str, kind: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    rid = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now)) + "-" + uuid.uuid4().hex[:6]
    d = Path(qdir)
    d.mkdir(parents=True, exist_ok=True)
    body = {"id": rid, "mode": mode, "by": by, "kind": kind, "ts": int(now), "expires": int(now + REQUEST_TTL_S)}
    tmp = d / f".req-{rid}.tmp"
    tmp.write_text(json.dumps(body), encoding="utf-8")
    os.replace(tmp, d / f"req-{rid}.json")          # atomic: the tray never reads a half-written file
    return rid


def _env_num(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, ""))
        return v if v >= 0 else default
    except ValueError:
        return default


@dataclass
class StartGate:
    max_workers: int = field(default_factory=lambda: min(HARD_MAX_WORKERS, int(_env_num("BOB_STARTWORKER_MAX", DEFAULT_MAX_WORKERS))))
    cooldown_s: float = field(default_factory=lambda: _env_num("BOB_STARTWORKER_COOLDOWN_S", DEFAULT_COOLDOWN_S))
    _last: float | None = None

    def remaining(self, now: float) -> float:
        return 0.0 if self._last is None else max(0.0, self.cooldown_s - (now - self._last))

    def arm(self, now: float) -> None:
        self._last = now


@dataclass
class Decision:
    ok: bool
    reason: str
    line: str
    mode: str = DEFAULT_MODE
    kind: str = ""
    request_id: str = ""


def decide(*, body: str, nick: str, account, channel: str, local_machine: str, gate: StartGate,
           qdir, home=None, machine_of_nick: Callable[[str], str | None], chair_nicks=("jeeves",),
           procs: Callable[[], list] | None = None, now: float | None = None,
           owners: set | None = None, write: bool = True) -> Decision | None:
    """None when ``body`` is not a !startworker command, else the ACK/NACK decision (request already queued)."""
    parsed = parse(body)
    if parsed is None:
        return None
    now = time.time() if now is None else now
    nack = lambda reason, text, **kw: Decision(False, reason, f"NACK startworker: {text}", **kw)   # noqa: E731
    if parsed == "usage":
        return nack("usage", usage())
    mode, machine = parsed
    ok, kind, why = authorize(nick, account, machine_of_nick=machine_of_nick, chair_nicks=chair_nicks, owners=owners)
    if not ok:
        return nack(why, "not verified (log in to your services account)" if why == "unverified"
                    else "denied (verified simon, Jeeves or a bob-* ear only)")
    local = (local_machine or "").strip().lower()
    chan = (channel or "").strip().lower().lstrip("#")
    if not local:
        return nack("no_machine", "this ear has no machine id")
    if machine is None:
        if chan != local:
            return nack("machine_required", "name the machine: !startworker [agent|plan] " + local, mode=mode, kind=kind)
        machine = local
    if machine != local:
        return None                                  # addressed to another machine's ear: not ours, stay silent
    if chan not in (local, "bobiverse") and channel:
        return nack("wrong_channel", f"use #{local} or #bobiverse", mode=mode, kind=kind)
    if home is not None and ((Path(home) / DISABLE_FILE).exists() or os.environ.get("BOB_STARTWORKER_DISABLE")):
        return nack("disabled", "remote start is disabled on this machine", mode=mode, kind=kind)
    if not tray_alive(qdir, now):
        return nack("no_interactive_session",
                    "nobody is logged in with the Bob tray running (start the tray from the Start menu)", mode=mode, kind=kind)
    # FR #2522: only agent starts are capped; plan may start on top of 2 workers.
    have = count_workers((procs or snapshot_procs)(), modes=("agent",))
    cap = min(gate.max_workers, HARD_MAX_WORKERS)
    if mode == "agent" and have >= cap:
        return nack("cap", f"max {cap} workers ({have} running on {local})", mode=mode, kind=kind)
    left = gate.remaining(now)
    if left > 0:
        return nack("cooldown", f"cooldown {int(left + 0.999)}s", mode=mode, kind=kind)
    rid = ""
    if write:
        try:
            rid = write_request(qdir, mode, nick, kind, now)
        except OSError as e:
            return nack("queue_error", f"could not queue the request ({type(e).__name__})", mode=mode, kind=kind)
    gate.arm(now)
    slot = (
        f"workers {have + 1}/{cap}" if mode == "agent"
        else f"plan (uncapped; workers {have}/{cap})"
    )
    return Decision(True, "ok", f"ACK startworker {mode} on {local} (queued {rid or '-'}; {slot}; by {nick})",
                    mode, kind, rid)