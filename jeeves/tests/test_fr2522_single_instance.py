"""FR #2522: only ONE maintenance agent — concurrent triggers spawn exactly one."""
from __future__ import annotations

from pathlib import Path

import jeeves_maintenance as jm


def test_fr2522_two_concurrent_triggers_one_agent(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "ai" / "jeeves"
    work.mkdir(parents=True)
    exe = tmp_path / "ai" / "bob" / "worker" / "bob-worker.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    spawned: list[int] = []

    def slow_spawn(exe_, bob, work_, *a):
        spawned.append(1)
        return 9000 + len(spawned)

    real_alive = jm._pid_alive
    jm._pid_alive = lambda pid: pid == 9001  # type: ignore[assignment]
    try:
        r1 = jm.try_start_maintenance_agent(
            home=home, heal_exit=1, now=10_000.0, cooldown_s=1.0,
            spawn_fn=slow_spawn, resolve_cwd=lambda: work, resolve_exe=lambda _c: exe,
        )
        r2 = jm.try_start_maintenance_agent(
            home=home, heal_exit=1, now=10_000.1, cooldown_s=1.0,
            spawn_fn=slow_spawn, resolve_cwd=lambda: work, resolve_exe=lambda _c: exe,
        )
        assert r1.action == "spawn" and r1.pid == 9001
        assert r2.action == "skip" and "already_live" in r2.reason
        assert spawned == [1]
        assert jm.read_lock(home)["pid"] == 9001
    finally:
        jm._pid_alive = real_alive  # type: ignore[assignment]


def test_fr2522_stale_lock_cleared_when_pid_dead(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "j"
    work.mkdir()
    jm.write_lock(home, 424242, str(work))
    real = jm._pid_alive
    jm._pid_alive = lambda pid: False  # type: ignore[assignment]
    try:
        assert jm.live_maintenance_pid(home) is None
        assert not (jm.state_dir(home) / jm.LOCK_NAME).is_file()
    finally:
        jm._pid_alive = real  # type: ignore[assignment]
