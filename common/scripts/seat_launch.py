"""FR #2413: one shared seat launch plan for tray / remote !startworker / CLI.

Tray (Start-BobTrayWorkerExe) and remote start both run bob-worker.exe with the same
argv + working folder. bob-worker then builds the agent/plan LaunchSpec + env via
:func:`shared_seat_plan` so prompt, skills path, and BOB_OUTBOX env never diverge.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class SeatLaunchPlan:
    mode: str  # agent | plan
    cwd: str
    run_dir: str
    prompt: str
    env_extra: dict = field(default_factory=dict)
    worker_argv: list = field(default_factory=list)  # bob-worker.exe argv (tray/CLI)
    worker_cwd: str = ""  # process cwd for bob-worker.exe (same as seat folder for tray)
    kind: str = ""
    exe: str = ""
    session_id: str = ""
    launch_argv: list = field(default_factory=list)  # inner agent argv once kind known
    files: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def seat_folder(mode: str, install_root: str | Path) -> Path:
    root = Path(install_root)
    if mode == "plan":
        return root / "plan"
    if mode == "agent":
        return root / "worker"
    raise ValueError(f"seat_folder only for agent|plan, got {mode!r}")


def worker_exe_argv(
    mode: str,
    install_root: str | Path,
    *,
    machine_id: str = "",
    exe_name: str = "bob-worker.exe",
) -> list[str]:
    """Exact argv Start-BobTrayWorkerExe / CLI must share (FR #2413)."""
    if mode not in ("agent", "plan"):
        raise ValueError(mode)
    argv = [exe_name, "--mode", mode, "--install-root", str(install_root)]
    mid = (machine_id or "").strip()
    if mid and mode == "agent":
        argv.extend(["--machine-id", mid])
    return argv


def tray_launch_contract(
    mode: str,
    install_root: str | Path,
    *,
    machine_id: str = "",
) -> dict:
    """Mirror of Start-BobTrayWorkerExe: FilePath bob-worker, argv, WorkingDirectory."""
    folder = seat_folder(mode, install_root)
    return {
        "exe_name": "bob-worker.exe",
        "argv": worker_exe_argv(mode, install_root, machine_id=machine_id),
        "working_directory": str(folder),
        "mode": mode,
    }


def cli_launch_contract(
    mode: str,
    install_root: str | Path,
    *,
    machine_id: str = "",
) -> dict:
    """CLI / other path must match the tray contract exactly."""
    return tray_launch_contract(mode, install_root, machine_id=machine_id)


def shared_seat_plan(
    mode: str,
    install_root: str | Path,
    *,
    machine: str = "",
    nick: str = "",
    run_dir: str | Path,
    kind: str = "",
    exe: str = "",
    session_id: Optional[str] = None,
    prompt_fn=None,
    build_launch_fn=None,
    seat_env_fn=None,
    note: str = "",
) -> SeatLaunchPlan:
    """Build the full seat launch (prompt + env + optional inner LaunchSpec).

    Call sites: bob_worker.run_agent / run_plan (and any future remote path that
    constructs an agent without going through those helpers).
    """
    folder = seat_folder(mode, install_root)
    mid = (machine or "").strip().lstrip("#")
    n = (nick or "").strip() or (f"{mid}-{Path(run_dir).name}" if mid else "")
    if prompt_fn is None:
        # late import to avoid cycles when used from bob_worker itself
        import bob_worker as bw
        if mode == "plan":
            prompt = bw.plan_prompt(str(folder))
        else:
            prompt = bw.worker_prompt(str(folder), str(run_dir), mid, n)
    else:
        prompt = prompt_fn(str(folder), str(run_dir), mid, n) if mode == "agent" else prompt_fn(str(folder))
    if note:
        prompt = prompt + " " + note
    env_extra = {}
    if mode == "agent":
        if seat_env_fn is None:
            import bob_worker as bw
            env_extra = dict(bw.seat_env_extra(run_dir, mid, n))
        else:
            env_extra = dict(seat_env_fn(run_dir, mid, n))
    plan = SeatLaunchPlan(
        mode=mode,
        cwd=str(folder),
        run_dir=str(run_dir),
        prompt=prompt,
        env_extra=env_extra,
        worker_argv=worker_exe_argv(mode, install_root, machine_id=mid),
        worker_cwd=str(folder),
        kind=kind or "",
        exe=exe or "",
        session_id=session_id or "",
    )
    if kind and exe and build_launch_fn is not None:
        spec = build_launch_fn(kind, mode if mode == "plan" else "agent", str(folder), prompt, exe, Path(run_dir), session_id)
        plan.launch_argv = list(spec.argv)
        plan.files = dict(spec.files)
        plan.session_id = spec.session_id
    elif kind and exe:
        import bob_worker as bw
        spec = bw.build_launch(kind, mode if mode == "plan" else "agent", str(folder), prompt, exe, Path(run_dir), session_id)
        plan.launch_argv = list(spec.argv)
        plan.files = dict(spec.files)
        plan.session_id = spec.session_id
    return plan
