"""FR #8247: OpenCode seat scratch under worktree; stop external_directory loops."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw


def test_fr8247_ensure_scratch_under_worktree_bob_tmp(tmp_path: Path):
    wt = tmp_path / "job"
    wt.mkdir()
    scratch = bw.ensure_opencode_job_scratch(wt)
    assert scratch == wt / ".bob" / "tmp"
    assert scratch.is_dir()
    # Idempotent.
    assert bw.ensure_opencode_job_scratch(wt) == scratch


def test_fr8247_apply_scratch_env_points_temp_at_worktree(tmp_path: Path):
    wt = tmp_path / "job"
    wt.mkdir()
    env = {"TEMP": r"C:\Windows\Temp", "TMP": r"C:\Windows\Temp", "PATH": "x"}
    out = bw.apply_opencode_scratch_env(env, wt)
    scratch = str(wt / ".bob" / "tmp")
    assert out["TEMP"] == scratch
    assert out["TMP"] == scratch
    assert out["TMPDIR"] == scratch
    assert out["BOB_OPENCODE_SCRATCH"] == scratch
    assert (wt / ".bob" / "tmp").is_dir()


def test_fr8247_format_turn_error_classifies_external_directory():
    cls, line = bw.format_opencode_turn_error(
        1,
        stderr="permission requested: external_directory (C:\\Users\\x\\AppData\\Local\\Temp\\opencode\\mrb); auto-rejecting",
        stdout="",
    )
    assert cls == "external-directory"
    assert "external_directory" in line.lower()


def test_fr8247_is_external_directory_reject():
    assert bw.is_external_directory_reject(
        "external-directory", "exit 1: auto-rejecting"
    )
    assert bw.is_external_directory_reject(
        "process-exit",
        "permission requested: external_directory (...); auto-rejecting",
    )
    assert not bw.is_external_directory_reject("epipe", "broken pipe")
    assert not bw.is_external_directory_reject("process-exit", "exit 1: something else")


def test_fr8247_loop_max_default_and_env(monkeypatch):
    monkeypatch.delenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", raising=False)
    assert bw.opencode_external_dir_loop_max() == 2
    monkeypatch.setenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", "3")
    assert bw.opencode_external_dir_loop_max() == 3
    monkeypatch.setenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", "0")
    assert bw.opencode_external_dir_loop_max() == 1  # clamp low
    monkeypatch.setenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", "99")
    assert bw.opencode_external_dir_loop_max() == 10  # clamp high


def test_fr8247_record_reject_corrective_then_giveup(monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", "2")
    state: dict = {}
    key = "MRB SimonBarnett/bobiverse#8224"
    assert bw.record_external_dir_reject(state, key) == "corrective"
    assert state["counts"][key] == 1
    assert state["corrective_pending"] is True
    assert bw.record_external_dir_reject(state, key) == "giveup"
    assert state["counts"][key] == 2


def test_fr8247_corrective_prompt_names_scratch(tmp_path: Path):
    wt = tmp_path / "job"
    scratch = bw.ensure_opencode_job_scratch(wt)
    text = bw.opencode_external_dir_corrective_steps(
        job_key="MRB SimonBarnett/bobiverse#8224",
        worktree=wt,
        outbox=wt / ".bob" / "outbox.txt",
        scratch=scratch,
    )
    low = text.lower()
    assert "external" in low or "scratch" in low or ".bob" in low
    assert str(scratch).lower() in low or ".bob\\tmp" in low or ".bob/tmp" in low
    assert "%temp%" not in low or "not" in low  # must not send them back to %TEMP%
    assert "external_directory" in low
    assert "never" in low or "do not" in low


def test_fr8247_bored_external_dir_loop_giveup(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", "2")
    logs: list[str] = []
    giveups: list[str] = []
    injects: list[str] = []

    bored = bw.BoredEmitter(lambda: True, logs.append, clock=lambda: 1000.0)
    bored._ack_open = True
    bored._ack_at = 900.0
    bored._ack_job_key = "MRB SimonBarnett/bobiverse#8224"
    # seat_release_giveup_fn(job_key, reason) — capture the reason for assertions.
    bored.seat_release_giveup_fn = lambda _job, why: giveups.append(why) or True
    bored.failed_turn_retry_fn = lambda key: injects.append(f"retry:{key}")
    bored.done_miss_remind_fn = lambda key: injects.append(f"remind:{key}")

    # First rejection -> corrective retry inject
    bored.turn_ended(
        at=1000.0,
        error=True,
        error_class="external-directory",
        error_line="exit 1: permission requested: external_directory; auto-rejecting",
    )
    assert giveups == []
    assert any(i.startswith("retry:") for i in injects)
    assert bored._ack_open is True

    # Second rejection -> giveup external-dir-loop
    injects.clear()
    bored.turn_ended(
        at=1001.0,
        error=True,
        error_class="external-directory",
        error_line="exit 1: permission requested: external_directory; auto-rejecting",
    )
    assert any("external-dir-loop" in g for g in giveups)
    assert injects == []


def test_fr8247_inject_done_miss_uses_corrective(monkeypatch, tmp_path: Path):
    wt = tmp_path / "job"
    scratch = bw.ensure_opencode_job_scratch(wt)
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(wt))
    lines: list[str] = []

    irc = SimpleNamespace(shop="#flamingo", say=lambda *_a, **_k: None)
    relay = SimpleNamespace(set_target=lambda *_a, **_k: None, last_unacked="")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    sup = bw.Supervisor(
        kind="opencode",
        exe=r"C:\o\opencode.exe",
        cwd=str(tmp_path),
        machine="flamingo",
        nick="flamingo-1",
        run_dir=str(run_dir),
        irc=irc,
        relay=relay,
        log=lambda _m: None,
        install_root=str(tmp_path),
        kill=lambda _pid: True,
        spawn=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no spawn")),
    )
    bored = bw.BoredEmitter(lambda: True, lambda _m: None, clock=lambda: 1.0)
    bored._ack_open = True
    bored._ack_job_key = "MRB SimonBarnett/bobiverse#8224"
    # Simulate one recorded reject waiting for corrective FINISH.
    bw.record_external_dir_reject(bored.external_dir_reject_state, bored._ack_job_key)
    bored.external_dir_reject_state["corrective_pending"] = True
    sup.bored = bored
    sup.proc = SimpleNamespace(pid=1, poll=lambda: None)
    monkeypatch.setattr(sup, "_inject_line", lambda proc, line: lines.append(line) or True)
    # Attribute is created on first OpenCode job; set directly for the unit test.
    sup._opencode_job_outbox = wt / ".bob" / "outbox.txt"

    sup._inject_done_miss_reminder(bored._ack_job_key)

    assert lines, "expected a corrective inject"
    blob = "\n".join(lines).lower()
    assert "external" in blob or "scratch" in blob or ".bob" in blob
    assert str(scratch).lower() in blob or ".bob" in blob
    # Corrective pending cleared after use.
    assert bored.external_dir_reject_state.get("corrective_pending") is False


def test_fr8247_wrapper_sets_temp_under_bob_tmp(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        r"C:\ai\bob\worker",
        "keep ticking",
        r"C:\opencode.exe",
        tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert ".bob" in script
    assert "tmp" in script.lower()
    assert "$env:TEMP" in script
    assert "$env:TMP" in script
    assert '"allow"' not in script
