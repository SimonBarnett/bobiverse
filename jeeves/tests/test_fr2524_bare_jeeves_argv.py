"""FR #2524: bare jeeves.exe must fail-fast (no mutex); maintenance state uses --home."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr
from pathlib import Path

import jeeves_main
import jeeves_maintenance as jm


def test_fr2524_bare_argv_exits_2_without_mutex(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    acquired = {"n": 0}

    def boom(*_a, **_k):
        acquired["n"] += 1
        return True

    monkeypatch.setattr("jeeves_locks.try_acquire_instance_mutex", boom)
    monkeypatch.setattr("jeeves_locks.enable_inproc_locks", lambda: None)
    monkeypatch.setattr("jeeves_locks.release_instance_mutex", lambda: None)
    err = io.StringIO()
    with redirect_stderr(err):
        code = jeeves_main.main([])
    assert code == 2
    assert acquired["n"] == 0
    assert "specify --self-test" in err.getvalue() or "mode" in err.getvalue().lower()


def test_fr2524_bare_argv_does_not_spawn_maintenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    spawned = {"n": 0}

    def fake_try(**kwargs):
        spawned["n"] += 1
        return jm.MaintenanceResult("spawn", "should_not_run")

    monkeypatch.setattr(jm, "try_start_maintenance_agent", fake_try)
    monkeypatch.setattr("jeeves_locks.enable_inproc_locks", lambda: None)
    monkeypatch.setattr("jeeves_locks.try_acquire_instance_mutex", lambda *_a, **_k: True)
    monkeypatch.setattr("jeeves_locks.release_instance_mutex", lambda: None)
    with redirect_stderr(io.StringIO()):
        code = jeeves_main.main([])
    assert code == 2
    assert spawned["n"] == 0


def test_fr2524_heal_maintenance_state_uses_chair_home(tmp_path):
    digest = tmp_path / "digest"
    chair = tmp_path / "chair"
    digest.mkdir()
    chair.mkdir()
    (tmp_path / "ai" / "jeeves").mkdir(parents=True)
    exe = tmp_path / "ai" / "bob" / "worker" / "bob-worker.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")

    def fake_spawn(_e, _b, _w):
        return 5555

    r = jm.try_start_maintenance_agent(
        home=chair,
        heal_exit=1,
        heal_payload={"findings": ["f1"], "errors": ["e1"]},
        now=1_000.0,
        cooldown_s=100.0,
        spawn_fn=fake_spawn,
        resolve_cwd=lambda: tmp_path / "ai" / "jeeves",
        resolve_exe=lambda _c: exe,
    )
    assert r.action == "spawn"
    st_path = jm.state_dir(chair) / jm.STATE_NAME
    assert st_path.is_file()
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert st.get("last_heal_findings") == ["f1"]
    assert st.get("last_heal_errors") == ["e1"]
    assert not (jm.state_dir(digest) / jm.STATE_NAME).is_file()


def test_fr2524_run_heal_passes_chair_home_to_maintenance(tmp_path, monkeypatch):
    digest = tmp_path / "d"
    chair = tmp_path / "c"
    digest.mkdir()
    chair.mkdir()
    seen = {}

    def fake_try(**kwargs):
        seen.update(kwargs)
        return jm.MaintenanceResult("skip", "heal_ok")

    monkeypatch.setattr("jeeves_maintenance.try_start_maintenance_agent", fake_try)
    (digest / "queue.json").write_text("{}", encoding="utf-8")
    code = jeeves_main.run_heal(
        home=digest,
        dry_run=True,
        force_orphan_busy=False,
        as_json=True,
        chair_home=chair,
        no_maintenance_agent=False,
    )
    assert code in (0, 1, 2)
    assert seen.get("home") == chair
    assert isinstance(seen.get("heal_payload"), dict)

def test_fr2524_nssm_assert_and_install_gate_sources():
    from repo_layout import ROOT
    assert_txt = (ROOT / "jeeves/scripts/Assert-BobJeevesNssmRestart.ps1").read_text(encoding="utf-8")
    assert "2524" in assert_txt and "AppParameters" in assert_txt
    inst = (ROOT / "jeeves/scripts/Install-Jeeves.ps1").read_text(encoding="utf-8")
    assert "FR #2524" in inst and "--chair" in inst
    doc = (ROOT / "jeeves/docs/jeeves-exe-self-heal.md").read_text(encoding="utf-8")
    assert "2524" in doc and "bare" in doc.lower()
