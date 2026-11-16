"""FR #7952: a pause fallback returns to the configured model on the next job."""
from __future__ import annotations

import json
import os

import bob.scripts.bob_worker as bw

FLASH = "opencode/deepseek-v4.1-flash-free"
BEAM = "opencode/beam-free"


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        json.dumps({"workerStartModels": {"opencode": FLASH}}),
    )
    bw._OPENCODE_MODEL_ENV_AT_START = None


def test_fallback_stays_on_beam_until_pause_expires_then_flash(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    now = 1_700_000_000.0
    state = tmp_path / "Bobiverse" / "worker" / "state"
    bw.opencode_fuel.save_opencode_pauses(state, {FLASH: now + 60})
    env = dict(os.environ)
    assert bw.stamp_opencode_pause_fallback(env, BEAM, now=now) is True
    assert env.get("BOB_OPENCODE_PAUSE_FALLBACK") == "1"
    published: list[tuple[str, bool]] = []

    def publish(model, mismatch):
        published.append((model, mismatch))

    during = bw.resume_opencode_pause_fallback(
        current=BEAM,
        configured=FLASH,
        state_dir=state,
        pause_fallback=True,
        now=now + 10,
        publish=publish,
    )
    assert during == BEAM
    assert published == []
    nxt = bw.resume_opencode_pause_fallback(
        current=BEAM,
        configured=FLASH,
        state_dir=state,
        pause_fallback=True,
        now=now + 120,
        publish=publish,
    )
    assert nxt == FLASH
    assert published == [(FLASH, False)]


def test_operator_chosen_model_is_not_a_fallback(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = BEAM
    now = 1_700_000_000.0
    state = tmp_path / "Bobiverse" / "worker" / "state"
    bw.opencode_fuel.save_opencode_pauses(state, {FLASH: now + 3600})
    env = dict(os.environ)
    assert bw.stamp_opencode_pause_fallback(env, BEAM, now=now) is False
    assert "BOB_OPENCODE_PAUSE_FALLBACK" not in env
    assert bw.opencode_fuel.next_job_model(
        BEAM, FLASH, state, now=now + 4000, pause_fallback=False
    ) == BEAM


def test_wrapper_resolves_fallback_once_per_job(tmp_path):
    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "prompt", "opencode.exe", tmp_path
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert script.count("next-model") == 1
    assert "BOB_OPENCODE_PAUSE_FALLBACK" in script
    start = script.find("function Invoke-OpencodeRun")
    run_loop = script.find("while (-not $proc.HasExited)", start)
    resume = script.find("next-model", start)
    assert 0 <= start < resume < run_loop
