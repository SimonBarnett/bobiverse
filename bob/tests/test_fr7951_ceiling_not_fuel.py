"""FR #7951: a hard-ceiling turn must not pause the OpenCode model."""
from __future__ import annotations

from pathlib import Path

import bob.scripts.bob_worker as bw


def test_hard_ceiling_does_not_write_pause_and_start_keeps_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    state = tmp_path / "state"
    model = "opencode/deepseek-v4.1-flash-free"
    for text in (
        "hard ceiling 1800000ms",
        "hard-ceiling 1800000ms",
        "hard ceiling 1800000ms\nHTTP 429 Too Many Requests",
        "watchdog timeout (no output/cpu/worktree idle 120000ms)",
    ):
        assert bw.opencode_fuel.record_opencode_pause(state, model, text, now=1_000_000.0) is None
    pause = state / "opencode-pauses.json"
    assert not pause.exists()
    assert bw.opencode_fuel.record_opencode_pause(
        state, model, "HTTP 429 Too Many Requests", now=1_000_000.0
    ) is not None
    pause.unlink()

    cfg = tmp_path / "opencode.json"
    cfg.write_text('{"model": "opencode/deepseek-v4.1-flash-free"}\n', encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = None
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    got = bw.resolve_opencode_model(fuel, state_dir=state, now=1_000_000.0)
    assert got == model


def test_wrapper_does_not_pause_on_timeout(tmp_path: Path):
    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "prompt", "opencode.exe", tmp_path
    )
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "-not $timedOut" in script
    assert bw.is_out_of_fuel_text(
        '{"pid":1,"model":"opencode/deepseek-v4.1-flash-free","text":"hard ceiling 1800000ms","pause":false}'
    ) is False
