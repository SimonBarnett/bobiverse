"""FR #2412: maintenance agent after heal fail — path, lock, rate-limit."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_root  # noqa: E402
import maintenance_agent as ma  # noqa: E402


def test_resolve_jeeves_cwd_prefers_ai_root(tmp_path, monkeypatch):
    d = tmp_path / "D"
    (d / "ai" / "jeeves").mkdir(parents=True)
    disks = [ai_root.Disk(str(d) + "\\", ai_root.DRIVE_FIXED)]
    # ai_root joins drive root + ai; Disk.root should look like "D:\\"
    # On Linux tests we pass absolute fake roots via override
    monkeypatch.setenv("BOB_AI_ROOT", str(tmp_path / "ai"))
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    cwd = ma.resolve_jeeves_cwd(env={"BOB_AI_ROOT": str(tmp_path / "ai")})
    assert cwd == tmp_path / "ai" / "jeeves"


def test_skip_when_heal_ok(tmp_path):
    home = tmp_path / "state"
    dec = ma.decide_start(
        heal_exit=0,
        state_home=home,
        env={"BOB_AI_ROOT": str(tmp_path / "ai"), "BOB_MAINT_STATE": str(home)},
    )
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    assert dec.ok is False
    assert dec.reason == "heal_ok"


def test_skip_dry_run(tmp_path):
    home = tmp_path / "state"
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    dec = ma.decide_start(
        heal_exit=1,
        dry_run=True,
        state_home=home,
        env={"BOB_AI_ROOT": str(tmp_path / "ai")},
    )
    assert dec.reason == "dry_run"


def test_single_instance_lock(tmp_path):
    home = tmp_path / "state"
    home.mkdir()
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    lock = home / ma.LOCK_NAME
    assert ma.acquire_lock(lock, pid=12345)
    assert ma.lock_held(lock, now=time.time(), stale_s=9999)
    assert not ma.acquire_lock(lock, pid=99)
    ma.release_lock(lock)
    assert ma.acquire_lock(lock, pid=1)


def test_cooldown(tmp_path):
    home = tmp_path / "state"
    home.mkdir()
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    (home / ma.STATE_NAME).write_text('{"last_spawn_ts": %s}' % time.time(), encoding="utf-8")
    dec = ma.decide_start(
        heal_exit=2,
        cooldown_s=3600,
        state_home=home,
        env={"BOB_AI_ROOT": str(tmp_path / "ai")},
    )
    assert dec.reason == "cooldown"


def test_spawn_after_heal_fail(tmp_path):
    home = tmp_path / "state"
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    seen = {}

    def spawn(cwd, prompt):
        seen["cwd"] = cwd
        seen["prompt"] = prompt
        return 4242

    dec = ma.start_maintenance_agent(
        heal_exit=1,
        state_home=home,
        env={"BOB_AI_ROOT": str(tmp_path / "ai")},
        spawn=spawn,
        now=1_700_000_000.0,
    )
    assert dec.ok and dec.reason == "spawned"
    assert dec.pid == 4242
    assert "jeeves" in seen["cwd"].replace("\\", "/")
    assert "MAINTENANCE" in seen["prompt"]
    # second call blocked by lock
    dec2 = ma.start_maintenance_agent(
        heal_exit=1,
        state_home=home,
        env={"BOB_AI_ROOT": str(tmp_path / "ai")},
        spawn=spawn,
        now=1_700_000_010.0,
    )
    assert dec2.reason == "already_running"
