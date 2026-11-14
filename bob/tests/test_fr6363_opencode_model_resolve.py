"""FR #6363: honour operator/OpenCode-config model before fuel default."""
from __future__ import annotations

from pathlib import Path

import bob.scripts.bob_worker as bw


def test_fr6363_strip_jsonc_comments_and_trailing_comma():
    raw = """
    {
      // Simon default
      "model": "opencode/deepseek-v4.1-flash-free", /* free */
      "theme": "opencode",
    }
    """
    doc = __import__("json").loads(bw._strip_jsonc(raw))
    assert doc["model"] == "opencode/deepseek-v4.1-flash-free"


def test_fr6363_env_beats_config_and_fuel(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text(
        '// cfg\n{ "model": "opencode/deepseek-v4.1-flash-free" }\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = "opencode/beam-free"
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    got = bw.resolve_opencode_model(
        fuel, state_dir=tmp_path, env=env, log_fn=logs.append
    )
    assert got == "opencode/beam-free"
    assert any("source=env" in line and "model=opencode/beam-free" in line for line in logs)


def test_fr6363_config_used_when_env_unset(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text(
        '{ // comment\n  "model": "opencode/deepseek-v4.1-flash-free",\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = None
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, log_fn=logs.append)
    assert got == "opencode/deepseek-v4.1-flash-free"
    assert any("source=config" in line for line in logs)


def test_fr6363_paused_config_falls_back_to_fuel(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.json"
    cfg.write_text('{"model": "opencode/deepseek-v4.1-flash-free"}', encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = None
    state = tmp_path / "state"
    now = 2_000_000.0
    # Persist a future pause without needing rate-limit output text.
    bw.opencode_fuel.save_opencode_pauses(state, {"opencode/deepseek-v4.1-flash-free": now + 3600})
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    got = bw.resolve_opencode_model(fuel, state_dir=state, now=now, log_fn=logs.append)
    assert got == "opencode/beam-free"
    assert any("source=fuel" in line for line in logs)
    assert any("paused" in line for line in logs)


def test_fr6363_neither_set_uses_fuel_unchanged(tmp_path):
    bw._OPENCODE_MODEL_ENV_AT_START = None
    env = {
        "OPENCODE_CONFIG": str(tmp_path / "missing.jsonc"),
        "XDG_CONFIG_HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "HOME": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path),
    }
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={},
        opencode_free_model_ids=("opencode/beam-free",),
    )
    logs: list[str] = []
    got = bw.resolve_opencode_model(
        fuel, state_dir=tmp_path, env=env, log_fn=logs.append
    )
    assert got == "opencode/deepseek-v4.1-flash-free"
    assert any("source=start" in line for line in logs)


def test_fr6363_worker_export_not_operator_override(tmp_path, monkeypatch):
    """Process-start capture only: later os.environ write is ignored for env source."""
    cfg = tmp_path / "opencode.json"
    cfg.write_text('{"model": "opencode/deepseek-v4.1-flash-free"}', encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = None
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode/beam-free")  # fake prior worker export
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, log_fn=logs.append)
    assert got == "opencode/deepseek-v4.1-flash-free"
    assert any("source=config" in line for line in logs)


def test_fr6363_capture_at_start_records_operator_env(monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode/deepseek-v4.1-flash-free")
    assert bw.capture_opencode_model_env_at_start() == "opencode/deepseek-v4.1-flash-free"
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode/beam-free")
    # capture again overwrites (process start is once; tests may re-call)
    assert bw.capture_opencode_model_env_at_start() == "opencode/beam-free"


def test_fr6363_all_launch_paths_use_resolver():
    text = Path(bw.__file__).read_text(encoding="utf-8")
    assert text.count("oc_model = resolve_opencode_model(fuel, log_fn=log)") == 4
    assert text.count("oc_model = opencode_default_model(fuel)") == 0
    assert "capture_opencode_model_env_at_start()" in text


def test_fr6363_star_free_recognised_when_configured(tmp_path, monkeypatch):
    """Explicit *-free config models are usable without OPENCODE_FREE_MODELS membership."""
    cfg = tmp_path / "opencode.json"
    cfg.write_text('{"model": "opencode/deepseek-v4.1-flash-free"}', encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    bw._OPENCODE_MODEL_ENV_AT_START = None
    # free pool available; deepseek not in OPENCODE_FREE_MODELS hard list
    assert "deepseek-v4.1-flash-free" not in bw.opencode_fuel.OPENCODE_FREE_MODELS
    fuel = bw.Fuel(opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    assert bw.resolve_opencode_model(fuel, state_dir=tmp_path) == "opencode/deepseek-v4.1-flash-free"
