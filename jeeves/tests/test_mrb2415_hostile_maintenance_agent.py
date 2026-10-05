"""MRB #2415 hostile: FR #2412 maintenance agent edges beyond tip coverage."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

import jeeves_maintenance as jm

MAIN = ROOT / "common/scripts/jeeves_main.py"
MAINT = ROOT / "common/scripts/jeeves_maintenance.py"
WORKER = ROOT / "bob/scripts/bob_worker.py"
START = ROOT / "jeeves/scripts/Start-JeevesMaintenance.ps1"
BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"


def test_mrb2415_cwd_prefers_first_letter_with_ai():
    cwd = jm.resolve_jeeves_maintenance_cwd(
        env={},
        drive_letters=["C", "D"],
        isdir=lambda p: p.lower() in (r"c:\ai", r"d:\ai"),
    )
    assert str(cwd).replace("/", "\\").lower() == r"c:\ai\jeeves"


def test_mrb2415_cwd_systemdrive_fallback():
    cwd = jm.resolve_jeeves_maintenance_cwd(
        env={"SystemDrive": "E:"},
        drive_letters=["C", "D"],
        isdir=lambda _p: False,
    )
    assert str(cwd).replace("/", "\\").lower() == r"e:\ai\jeeves"


def test_mrb2415_dead_lock_pid_clears_and_allows_spawn(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "ai" / "jeeves"
    work.mkdir(parents=True)
    exe = tmp_path / "ai" / "bob" / "worker" / "bob-worker.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    jm.write_lock(home, 999001, str(work))
    real_alive = jm._pid_alive
    jm._pid_alive = lambda pid: False  # type: ignore[assignment]
    spawned: list[int] = []
    try:
        r = jm.try_start_maintenance_agent(
            home=home,
            heal_exit=1,
            now=2_000.0,
            cooldown_s=1.0,
            spawn_fn=lambda *_a: (spawned.append(1) or 5555),
            resolve_cwd=lambda: work,
            resolve_exe=lambda _c: exe,
        )
        assert r.action == "spawn" and r.pid == 5555
        assert spawned == [1]
        assert jm.read_lock(home)["pid"] == 5555
    finally:
        jm._pid_alive = real_alive  # type: ignore[assignment]


def test_mrb2415_bob_worker_missing_skips(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    work = tmp_path / "j"
    work.mkdir()
    r = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=3,
        now=3_000.0,
        cooldown_s=1.0,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: None,
    )
    assert r.action == "skip" and r.reason == "bob_worker_missing"
    log = (jm.state_dir(home) / jm.LOG_NAME).read_text(encoding="utf-8")
    assert "bob_worker_missing" in log
    assert not (jm.state_dir(home) / jm.LOCK_NAME).is_file()


def test_mrb2415_dry_run_would_spawn_without_lock_or_cooldown(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    work = tmp_path / "j"
    work.mkdir()
    exe = tmp_path / "bob-worker.exe"
    exe.write_bytes(b"MZ")
    spawned: list = []
    r = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=1,
        dry_run=True,
        now=4_000.0,
        cooldown_s=60.0,
        spawn_fn=lambda *a: spawned.append(a) or 1,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: exe,
    )
    assert r.action == "dry-run" and r.reason == "would_spawn"
    assert spawned == []
    assert not (jm.state_dir(home) / jm.LOCK_NAME).is_file()
    assert jm.read_state(home).get("last_spawn_ts") in (None, 0, 0.0)
    assert "would_spawn" in (jm.state_dir(home) / jm.LOG_NAME).read_text(encoding="utf-8")


def test_mrb2415_spawn_failed_logged(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    work = tmp_path / "j"
    work.mkdir()
    exe = tmp_path / "bob-worker.exe"
    exe.write_bytes(b"MZ")

    def boom(*_a):
        raise RuntimeError("nope")

    r = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=1,
        now=5_000.0,
        cooldown_s=1.0,
        spawn_fn=boom,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: exe,
    )
    assert r.action == "skip" and "spawn_failed" in r.reason
    assert "RuntimeError" in r.reason


def test_mrb2415_spawn_uses_create_new_console_and_maintenance_mode():
    text = MAINT.read_text(encoding="utf-8")
    assert "CREATE_NEW_CONSOLE" in text
    assert '"--mode"' in text or "'--mode'" in text
    assert "maintenance" in text
    assert "MAINTENANCE_COOLDOWN_S = 30 * 60" in text


def test_mrb2415_worker_prompt_cast_iron():
    text = WORKER.read_text(encoding="utf-8")
    assert "def maintenance_prompt" in text
    assert "never Ergo" in text or "never Ergo/BobIrcd" in text
    assert "Report-BobiverseIntakeIssue" in text
    assert ("NEW maintenance session" in text) or ("RESUMES your previous maintenance session" in text) or ("NEW session" in text)
    assert '"maintenance"' in text
    # hashed Start-JeevesMaintenance launcher
    st = START.read_text(encoding="utf-8-sig")
    assert "bob-worker-" in st and "Get-FileHash" in st
    assert "--mode" in st and "maintenance" in st
    assert "jeeves_maintenance" in BUILD.read_text(encoding="utf-8")
    assert "no_maintenance_agent" in MAIN.read_text(encoding="utf-8")


def test_mrb2415_encoding_no_bom():
    for path in (MAINT, MAIN, START, WORKER, Path(__file__)):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
