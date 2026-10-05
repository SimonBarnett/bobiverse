"""FR #2412: after --heal still failing, one rate-limited maintenance agent in \\ai\\jeeves."""
from __future__ import annotations

import json
from pathlib import Path

from repo_layout import ROOT

import jeeves_maintenance as jm
import jeeves_main

MAIN = ROOT / "common/scripts/jeeves_main.py"
MAINT = ROOT / "common/scripts/jeeves_maintenance.py"
WORKER = ROOT / "bob/scripts/bob_worker.py"
START = ROOT / "jeeves/scripts/Start-JeevesMaintenance.ps1"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
THIS = Path(__file__)
MOJIBAKE_DASH = ("\u00e2" + "\u20ac")


def test_fr2412_resolve_cwd_first_ai_drive():
    cwd = jm.resolve_jeeves_maintenance_cwd(
        env={},
        drive_letters=["C", "D", "E"],
        isdir=lambda p: p.lower() in (r"d:\ai",),
    )
    assert str(cwd).replace("/", "\\").lower() == r"d:\ai\jeeves"


def test_fr2412_resolve_cwd_bob_ai_root_override():
    cwd = jm.resolve_jeeves_maintenance_cwd(
        env={"BOB_AI_ROOT": r"E:\custom\ai"},
        drive_letters=["C"],
        isdir=lambda p: False,
    )
    assert str(cwd).replace("/", "\\").lower().endswith(r"e:\custom\ai\jeeves")


def test_fr2412_lock_and_cooldown(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    spawned: list[tuple] = []

    def fake_spawn(exe, bob, work):
        spawned.append((exe, bob, work))
        return 4242

    def fake_cwd():
        return tmp_path / "ai" / "jeeves"

    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    exe = tmp_path / "ai" / "bob" / "worker" / "bob-worker.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")

    r1 = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=1,
        dry_run=False,
        now=1_000.0,
        cooldown_s=100.0,
        spawn_fn=fake_spawn,
        resolve_cwd=fake_cwd,
        resolve_exe=lambda _c: exe,
    )
    assert r1.action == "spawn"
    assert r1.pid == 4242
    assert len(spawned) == 1
    log = (jm.state_dir(home) / jm.LOG_NAME).read_text(encoding="utf-8")
    assert "spawn" in log and "heal_still_failing" in log

    # single-instance: pretend PID still live via lock without clearing
    jm.write_lock(home, 4242, str(fake_cwd()))
    # monkey: force live by patching _pid_alive
    real_alive = jm._pid_alive
    jm._pid_alive = lambda pid: pid == 4242  # type: ignore[assignment]
    try:
        r2 = jm.try_start_maintenance_agent(
            home=home,
            heal_exit=1,
            now=1_010.0,
            cooldown_s=100.0,
            spawn_fn=fake_spawn,
            resolve_cwd=fake_cwd,
            resolve_exe=lambda _c: exe,
        )
        assert r2.action == "skip"
        assert "already_live" in r2.reason
    finally:
        jm._pid_alive = real_alive  # type: ignore[assignment]
        jm.clear_lock(home)

    # cooldown after prior spawn
    r3 = jm.try_start_maintenance_agent(
        home=home,
        heal_exit=2,
        now=1_050.0,
        cooldown_s=100.0,
        spawn_fn=fake_spawn,
        resolve_cwd=fake_cwd,
        resolve_exe=lambda _c: exe,
    )
    assert r3.action == "skip"
    assert "cooldown" in r3.reason
    assert len(spawned) == 1


def test_fr2412_heal_ok_skips(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    r = jm.try_start_maintenance_agent(home=home, heal_exit=0)
    assert r.action == "skip" and r.reason == "heal_ok"


def test_fr2412_heal_hook_wires_maintenance():
    text = MAIN.read_text(encoding="utf-8")
    assert "jeeves_maintenance" in text
    assert "try_start_maintenance_agent" in text
    assert "no_maintenance_agent" in text
    assert "2412" in text
    assert "maintenance" in text


def test_fr2412_bob_worker_maintenance_mode():
    text = WORKER.read_text(encoding="utf-8")
    assert '"maintenance"' in text or "'maintenance'" in text
    assert "maintenance_prompt" in text
    assert "run_maintenance" in text
    assert "FR #2412" in text or "FR #2412" in text


def test_fr2412_start_script_and_docs():
    assert START.is_file()
    st = START.read_text(encoding="utf-8-sig")
    assert "--mode" in st and "maintenance" in st
    assert "2412" in st
    doc = DOC.read_text(encoding="utf-8")
    assert "2412" in doc
    assert "maintenance" in doc.lower()


def test_fr2412_encoding_utf8_no_bom():
    for path in (MAINT, MAIN, START, THIS):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        assert raw.endswith(b"\n"), path
        if path != THIS:
            assert MOJIBAKE_DASH not in raw.decode("utf-8")
