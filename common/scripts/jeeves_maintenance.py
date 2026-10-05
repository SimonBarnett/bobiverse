"""FR #2412: after jeeves --heal still failing, start ONE rate-limited maintenance agent.

CWD is ``<drive>:\\ai\\jeeves`` where ``<drive>`` is the first fixed disk (C, D, E, ...)
that already has an ``ai`` folder (``BOB_AI_ROOT`` overrides). Never spawn while a
maintenance agent is already live; cooldown is logged on every skip/spawn.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

# Rate-limit between successful spawn attempts (seconds).
MAINTENANCE_COOLDOWN_S = 30 * 60
LOCK_NAME = "jeeves-maintenance.lock"
STATE_NAME = "jeeves-maintenance-state.json"
LOG_NAME = "jeeves-maintenance.log"


@dataclass
class MaintenanceResult:
    action: str  # spawn | skip | dry-run
    reason: str
    cwd: str = ""
    pid: int | None = None
    log_line: str = ""


def _norm(p: str) -> str:
    return str(p).replace("/", "\\").rstrip("\\")


def resolve_jeeves_maintenance_cwd(
    *,
    env: dict | None = None,
    drive_letters: Sequence[str] | None = None,
    isdir: Callable[[str], bool] | None = None,
) -> Path:
    """``<drive>:\\ai\\jeeves`` — first fixed letter with ``\\ai``, or BOB_AI_ROOT\\jeeves."""
    e = os.environ if env is None else env
    override = (e.get("BOB_AI_ROOT") or "").strip()
    check = isdir or os.path.isdir
    if override:
        return Path(_norm(override)) / "jeeves"
    letters = drive_letters
    if letters is None:
        letters = []
        try:
            import ctypes

            mask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
            for i in range(26):
                if mask & (1 << i):
                    root = f"{chr(65 + i)}:\\"
                    dt = int(ctypes.windll.kernel32.GetDriveTypeW(root))  # type: ignore[attr-defined]
                    if dt == 3:  # DRIVE_FIXED
                        letters.append(chr(65 + i))
        except Exception:
            letters = ["C", "D", "E", "F"]
    for letter in letters:
        L = letter.rstrip(":\\").upper()
        ai = f"{L}:\\ai"
        if check(ai):
            return Path(ai) / "jeeves"
    sysd = (e.get("SystemDrive") or "C:").rstrip("\\")
    return Path(f"{sysd}\\ai\\jeeves")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def state_dir(home: Path) -> Path:
    d = Path(home) / "maintenance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_log(home: Path, line: str) -> None:
    path = state_dir(home) / LOG_NAME
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {line}\n")
    except OSError:
        pass


def read_lock(home: Path) -> dict[str, Any] | None:
    path = state_dir(home) / LOCK_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def write_lock(home: Path, pid: int, cwd: str) -> None:
    path = state_dir(home) / LOCK_NAME
    path.write_text(
        json.dumps({"pid": int(pid), "cwd": cwd, "ts": time.time()}, indent=0) + "\n",
        encoding="utf-8",
    )


def clear_lock(home: Path) -> None:
    path = state_dir(home) / LOCK_NAME
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def read_state(home: Path) -> dict[str, Any]:
    path = state_dir(home) / STATE_NAME
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def write_state(home: Path, doc: dict[str, Any]) -> None:
    path = state_dir(home) / STATE_NAME
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def live_maintenance_pid(home: Path) -> int | None:
    lock = read_lock(home)
    if not lock:
        return None
    try:
        pid = int(lock.get("pid") or 0)
    except (TypeError, ValueError):
        clear_lock(home)
        return None
    if _pid_alive(pid):
        return pid
    clear_lock(home)
    return None


def cooldown_remaining(home: Path, now: float | None = None, cooldown_s: float = MAINTENANCE_COOLDOWN_S) -> float:
    st = read_state(home)
    last = float(st.get("last_spawn_ts") or 0)
    if last <= 0:
        return 0.0
    t = time.time() if now is None else now
    left = cooldown_s - (t - last)
    return left if left > 0 else 0.0


def resolve_bob_worker_exe(jeeves_cwd: Path) -> Path | None:
    ai = jeeves_cwd.parent
    cand = ai / "bob" / "worker" / "bob-worker.exe"
    if cand.is_file():
        return cand
    return None


def _spawn_bob_worker(exe: Path, bob_install: Path, work_root: Path) -> int:
    """Start bob-worker --mode maintenance in a new process; return pid."""
    argv = [
        str(exe),
        "--mode",
        "maintenance",
        "--install-root",
        str(bob_install),
        "--work-root",
        str(work_root),
    ]
    # Visible console for the ONE maintenance agent window (parity with Start-JeevesMonitor).
    creation = 0
    if os.name == "nt":
        creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    proc = subprocess.Popen(
        argv,
        cwd=str(work_root),
        close_fds=True,
        creationflags=creation,
    )
    return int(proc.pid)


def try_start_maintenance_agent(
    *,
    home: Path,
    heal_exit: int,
    heal_payload: dict[str, Any] | None = None,
    dry_run: bool = False,
    now: float | None = None,
    cooldown_s: float = MAINTENANCE_COOLDOWN_S,
    spawn_fn: Callable[[Path, Path, Path], int] | None = None,
    resolve_cwd: Callable[[], Path] | None = None,
    resolve_exe: Callable[[Path], Path | None] | None = None,
) -> MaintenanceResult:
    """If heal still failing, start one maintenance agent (or skip with logged reason)."""
    t = time.time() if now is None else now
    if int(heal_exit) == 0:
        r = MaintenanceResult("skip", "heal_ok")
        r.log_line = f"skip reason={r.reason}"
        _append_log(home, r.log_line)
        return r

    cwd = (resolve_cwd or resolve_jeeves_maintenance_cwd)()
    live = live_maintenance_pid(home)
    if live is not None:
        r = MaintenanceResult("skip", f"already_live pid={live}", cwd=str(cwd), pid=live)
        r.log_line = f"skip reason={r.reason} cwd={cwd}"
        _append_log(home, r.log_line)
        return r

    left = cooldown_remaining(home, now=t, cooldown_s=cooldown_s)
    if left > 0:
        r = MaintenanceResult("skip", f"cooldown_s={int(left)}", cwd=str(cwd))
        r.log_line = f"skip reason={r.reason} cwd={cwd}"
        _append_log(home, r.log_line)
        return r

    if dry_run:
        r = MaintenanceResult("dry-run", "would_spawn", cwd=str(cwd))
        r.log_line = f"dry-run reason={r.reason} cwd={cwd} heal_exit={heal_exit}"
        _append_log(home, r.log_line)
        return r

    find_exe = resolve_exe or resolve_bob_worker_exe
    exe = find_exe(Path(cwd))
    if exe is None:
        r = MaintenanceResult("skip", "bob_worker_missing", cwd=str(cwd))
        r.log_line = f"skip reason={r.reason} cwd={cwd}"
        _append_log(home, r.log_line)
        return r

    bob_install = exe.parent.parent  # .../bob/worker/bob-worker.exe -> bob
    spawner = spawn_fn or _spawn_bob_worker
    try:
        pid = int(spawner(exe, bob_install, Path(cwd)))
    except Exception as exc:  # noqa: BLE001
        r = MaintenanceResult("skip", f"spawn_failed:{type(exc).__name__}", cwd=str(cwd))
        r.log_line = f"skip reason={r.reason} cwd={cwd}"
        _append_log(home, r.log_line)
        return r

    write_lock(home, pid, str(cwd))
    st = read_state(home)
    st["last_spawn_ts"] = t
    st["last_pid"] = pid
    st["last_cwd"] = str(cwd)
    st["last_heal_exit"] = int(heal_exit)
    if heal_payload:
        st["last_heal_findings"] = list(heal_payload.get("findings") or [])[:20]
        st["last_heal_errors"] = list(heal_payload.get("errors") or [])[:20]
    write_state(home, st)
    r = MaintenanceResult("spawn", "heal_still_failing", cwd=str(cwd), pid=pid)
    r.log_line = f"spawn reason={r.reason} pid={pid} cwd={cwd} heal_exit={heal_exit}"
    _append_log(home, r.log_line)
    return r
