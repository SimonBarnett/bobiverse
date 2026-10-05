r"""FR #2412: after Jeeves self-heal still failing, start ONE rate-limited maintenance agent.

Working folder = <first existing drive>:\ai\jeeves (via ai_root). Single-instance lock + cooldown.
Logs every spawn/skip. Never touches BobIrcd/Ergo. Uses bob-worker --mode monitor when available,
else a dry plan record for tests.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_COOLDOWN_S = 3600.0
LOCK_NAME = "maintenance_agent.lock"
STATE_NAME = "maintenance_agent.json"
LOG_NAME = "maintenance_agent.log"


def resolve_jeeves_cwd(
    *,
    env: Optional[dict] = None,
    disks=None,
    services=None,
    system_drive: Optional[str] = None,
) -> Path:
    """First existing <drive>:\\ai\\jeeves (BOB_AI_ROOT / ai_root rule)."""
    import ai_root

    root = ai_root.product_root(
        "jeeves",
        env=env,
        disks=disks,
        services=services,
        system_drive=system_drive,
    )
    return Path(root)


def state_dir(jeeves_cwd: Path | None = None, env: Optional[dict] = None) -> Path:
    e = os.environ if env is None else env
    override = (e.get("BOB_MAINT_STATE") or "").strip()
    if override:
        return Path(override)
    base = jeeves_cwd or resolve_jeeves_cwd(env=e)
    return Path(base) / "run" / "maintenance"


@dataclass
class Decision:
    ok: bool
    reason: str
    cwd: str = ""
    pid: int = 0
    log_line: str = ""


def _read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(path)


def _log(path: Path, line: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    full = f"{stamp} {line}"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(full + "\n")
    except Exception:
        pass
    return full


def lock_held(lock_path: Path, *, now: float | None = None, stale_s: float = 7200.0) -> bool:
    """True when a non-stale lock file exists (single-instance).

    Fresh locks are held even if the recorded pid is gone: auto-unlink only after
    stale_s so a short-lived spawn cannot clear the lock before cooldown/state
    take over. Never treat a fresh lock as free.
    """
    if not lock_path.is_file():
        return False
    try:
        age = (now or time.time()) - lock_path.stat().st_mtime
        if age > stale_s:
            try:
                lock_path.unlink()
            except OSError:
                pass
            return False
        return True
    except Exception:
        return True


def acquire_lock(lock_path: Path, pid: int | None = None) -> bool:
    if lock_held(lock_path):
        return False
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(pid or os.getpid()))
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def maintenance_prompt(jeeves_dir: str) -> str:
    return (
        f"You are the Jeeves MAINTENANCE agent (FR #2412). NEW session only (never resume). "
        f"CWD is {jeeves_dir}. Jeeves self-heal still reported failure. "
        f"FIRST read {jeeves_dir}\\AGENTS.md and skills under {jeeves_dir}\\.grok\\skills. "
        f"Diagnose why Jeeves is unhealthy, apply safe fixes only (never touch BobIrcd/Ergo), "
        f"then file ONE GitHub issue in SimonBarnett/bobiverse describing the diagnosis and what you did "
        f"(use {jeeves_dir}\\scripts\\Report-BobiverseIntakeIssue.ps1). "
        f"CAST IRON: never print or store secrets. Exit when diagnosis+issue are done."
    )


def decide_start(
    *,
    heal_exit: int,
    dry_run: bool = False,
    cooldown_s: float = DEFAULT_COOLDOWN_S,
    now: float | None = None,
    env: Optional[dict] = None,
    disks=None,
    state_home: Path | None = None,
) -> Decision:
    """Pure-ish gate: whether to spawn after heal. Does not spawn."""
    t = now if now is not None else time.time()
    e = os.environ if env is None else env
    try:
        cwd = resolve_jeeves_cwd(env=e, disks=disks)
    except Exception as exc:
        return Decision(False, f"resolve_failed:{type(exc).__name__}")
    if not cwd.is_dir() and disks is None and "BOB_AI_ROOT" not in (e or {}):
        # allow missing dir in live resolve — still report path
        pass
    home = state_home or state_dir(cwd, env=e)
    log_path = home / LOG_NAME
    if dry_run:
        line = _log(log_path, f"skip dry_run heal_exit={heal_exit} cwd={cwd}")
        return Decision(False, "dry_run", cwd=str(cwd), log_line=line)
    if int(heal_exit) == 0:
        line = _log(log_path, f"skip heal_ok cwd={cwd}")
        return Decision(False, "heal_ok", cwd=str(cwd), log_line=line)
    lock_path = home / LOCK_NAME
    if lock_held(lock_path, now=t):
        line = _log(log_path, f"skip already_running lock={lock_path}")
        return Decision(False, "already_running", cwd=str(cwd), log_line=line)
    st = _read_state(home / STATE_NAME)
    last = float(st.get("last_spawn_ts") or 0)
    if last and (t - last) < float(cooldown_s):
        left = int(float(cooldown_s) - (t - last))
        line = _log(log_path, f"skip cooldown left_s={left} cwd={cwd}")
        return Decision(False, "cooldown", cwd=str(cwd), log_line=line)
    line = _log(log_path, f"allow spawn heal_exit={heal_exit} cwd={cwd}")
    return Decision(True, "ok", cwd=str(cwd), log_line=line)


def start_maintenance_agent(
    *,
    heal_exit: int,
    dry_run: bool = False,
    cooldown_s: float = DEFAULT_COOLDOWN_S,
    now: float | None = None,
    env: Optional[dict] = None,
    disks=None,
    state_home: Path | None = None,
    spawn: Optional[Callable[[str, str], int]] = None,
    install_root: str | Path | None = None,
) -> Decision:
    """Gate + single-instance lock + spawn. ``spawn(cwd, prompt) -> pid`` injectable."""
    t = now if now is not None else time.time()
    e = dict(os.environ if env is None else env)
    dec = decide_start(
        heal_exit=heal_exit,
        dry_run=dry_run,
        cooldown_s=cooldown_s,
        now=t,
        env=e,
        disks=disks,
        state_home=state_home,
    )
    if not dec.ok:
        return dec
    cwd = Path(dec.cwd)
    home = state_home or state_dir(cwd, env=e)
    lock_path = home / LOCK_NAME
    log_path = home / LOG_NAME
    if not acquire_lock(lock_path):
        line = _log(log_path, f"skip race_lock cwd={cwd}")
        return Decision(False, "already_running", cwd=str(cwd), log_line=line)
    prompt = maintenance_prompt(str(cwd))
    pid = 0
    try:
        if spawn is not None:
            pid = int(spawn(str(cwd), prompt) or 0)
        else:
            pid = _default_spawn(str(cwd), prompt, install_root=install_root, env=e)
        if pid <= 0:
            release_lock(lock_path)
            line = _log(log_path, f"skip launch_failed cwd={cwd}")
            return Decision(False, "launch_failed", cwd=str(cwd), log_line=line)
        _write_state(
            home / STATE_NAME,
            {"last_spawn_ts": t, "last_pid": pid, "last_cwd": str(cwd), "heal_exit": int(heal_exit)},
        )
        # rewrite lock with child pid
        try:
            lock_path.write_text(str(pid), encoding="utf-8")
        except OSError:
            pass
        line = _log(log_path, f"spawned pid={pid} cwd={cwd} heal_exit={heal_exit}")
        return Decision(True, "spawned", cwd=str(cwd), pid=pid, log_line=line)
    except Exception as exc:
        release_lock(lock_path)
        line = _log(log_path, f"skip error:{type(exc).__name__} cwd={cwd}")
        return Decision(False, f"error:{type(exc).__name__}", cwd=str(cwd), log_line=line)


def _default_spawn(
    cwd: str,
    prompt: str,
    *,
    install_root: str | Path | None = None,
    env: Optional[dict] = None,
) -> int:
    """Prefer bob-worker.exe --mode monitor --work-root <jeeves>; else 0."""
    import subprocess

    e = dict(os.environ if env is None else env)
    roots = []
    if install_root:
        roots.append(Path(install_root))
    try:
        import ai_root
        roots.append(Path(ai_root.product_root("bob", env=e)))
    except Exception:
        pass
    roots.append(Path(cwd).parent / "bob")
    exe = None
    for r in roots:
        cand = r / "worker" / "bob-worker.exe"
        if cand.is_file():
            exe = cand
            break
        cand2 = r / "bob-worker.exe"
        if cand2.is_file():
            exe = cand2
            break
    if exe is None:
        return 0
    argv = [str(exe), "--mode", "monitor", "--work-root", cwd, "--install-root", str(exe.parent.parent if exe.parent.name == "worker" else exe.parent)]
    # Pass prompt via env so we do not put it on the command line; monitor mode builds its own prompt.
    # Override with BOB_MAINT_PROMPT for the child if bob-worker grows support; for now monitor_prompt is close enough.
    e["BOB_MAINT_MODE"] = "1"
    e["BOB_MAINT_PROMPT"] = prompt[:4000]
    try:
        # DETACHED so heal CLI can exit; CREATE_NEW_CONSOLE when available
        flags = 0
        if os.name == "nt":
            flags = 0x00000010  # CREATE_NEW_CONSOLE
        proc = subprocess.Popen(argv, cwd=cwd, env=e, creationflags=flags, close_fds=True)
        return int(proc.pid)
    except Exception:
        return 0


def maybe_after_heal(
    heal_exit: int,
    *,
    dry_run: bool = False,
    as_json: bool = False,
    **kw: Any,
) -> Decision:
    """Entry used by jeeves_main.run_heal."""
    dec = start_maintenance_agent(heal_exit=heal_exit, dry_run=dry_run, **kw)
    if as_json:
        print(json.dumps({"maintenance": asdict(dec)}, separators=(",", ":")), flush=True)
    else:
        print(
            f"INFO maintenance ok={int(dec.ok)} reason={dec.reason} pid={dec.pid} cwd={dec.cwd}",
            flush=True,
        )
    return dec
