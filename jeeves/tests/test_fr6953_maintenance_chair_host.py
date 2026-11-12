"""FR #6953: heal/maintenance must not spawn a chair on non-walrus hosts."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_maintenance as jm
import jeeves_main


def test_fr6953_non_chair_skip_not_spawn(tmp_path: Path):
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
        cooldown_s=1.0,
        spawn_fn=lambda *a: spawned.append(a) or 1,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: exe,
        is_chair_host=False,
    )
    assert r.action == "skip"
    assert r.reason == "not_chair_host"
    assert spawned == []
    log = (jm.state_dir(home) / jm.LOG_NAME).read_text(encoding="utf-8")
    assert "skip reason=not_chair_host" in log
    assert "would_spawn" not in log


def test_fr6953_walrus_still_would_spawn_when_heal_fails(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    work = tmp_path / "j"
    work.mkdir()
    exe = tmp_path / "bob-worker.exe"
    exe.write_bytes(b"MZ")
    r = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=1,
        dry_run=True,
        now=4_000.0,
        cooldown_s=1.0,
        spawn_fn=lambda *a: 1,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: exe,
        is_chair_host=True,
    )
    assert r.action == "dry-run" and r.reason == "would_spawn"


def test_fr6953_walrus_spawns_when_chair_down(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    work = tmp_path / "ai" / "jeeves"
    work.mkdir(parents=True)
    exe = tmp_path / "ai" / "bob" / "worker" / "bob-worker.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    spawned: list[int] = []
    r = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=1,
        now=5_000.0,
        cooldown_s=1.0,
        spawn_fn=lambda *_a: spawned.append(1) or 4242,
        resolve_cwd=lambda: work,
        resolve_exe=lambda _c: exe,
        is_chair_host=True,
    )
    assert r.action == "spawn" and r.pid == 4242
    assert spawned == [1]


def test_fr6953_run_heal_non_chair_exits_0(tmp_path, monkeypatch):
    digest = tmp_path / "d"
    chair = tmp_path / "c"
    digest.mkdir()
    chair.mkdir()
    (digest / "queue.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(jm, "is_configured_chair_host", lambda env=None: False)

    code = jeeves_main.run_heal(
        home=digest,
        dry_run=True,
        force_orphan_busy=False,
        as_json=True,
        chair_home=chair,
        no_maintenance_agent=False,
    )
    assert code == 0
    log = (jm.state_dir(chair) / jm.LOG_NAME).read_text(encoding="utf-8")
    assert "skip reason=not_chair_host" in log
    assert "would_spawn" not in log


def test_fr6953_pins():
    maint = Path(__file__).resolve().parents[2] / "common" / "scripts" / "jeeves_maintenance.py"
    text = maint.read_text(encoding="utf-8")
    assert "not_chair_host" in text
    assert "FR #6953" in text
    assert "is_chair_host" in text
    main = Path(__file__).resolve().parents[2] / "common" / "scripts" / "jeeves_main.py"
    assert "not_chair_host" in main.read_text(encoding="utf-8")
