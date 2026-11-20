"""FR #8454: free-first resolve + launch wrapper end-of-turn switch pins."""
from __future__ import annotations

from pathlib import Path

import bob.scripts.bob_worker as bw


def _isolate_tray(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    monkeypatch.delenv("BOB_SEAT_MODEL_PIN", raising=False)


def test_fr8454_default_model_prefers_free_even_with_per_model_go():
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={"glm-5.3": 50, "kimi-k3": 40},
        opencode_free_model_ids=("opencode/beam-free",),
    )
    assert bw.opencode_default_model(fuel) == "opencode/beam-free"


def test_fr8454_resolve_skips_paid_env_when_free_available(tmp_path, monkeypatch):
    _isolate_tray(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = "opencode-go/deepseek-v4-pro"
    logs: list[str] = []
    fuel = bw.Fuel(
        opencode_free=80,
        opencode_go=50,
        opencode_free_model_ids=("opencode/deepseek-v4.1-flash-free",),
    )
    env = {"LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env, log_fn=logs.append)
    assert got == "opencode/deepseek-v4.1-flash-free"
    assert any("free-first" in line for line in logs)


def test_fr8454_resolve_paid_pin_yields_when_free_available(tmp_path, monkeypatch):
    _isolate_tray(monkeypatch, tmp_path)
    monkeypatch.setenv("BOB_SEAT_MODEL_PIN", "1")
    bw._OPENCODE_MODEL_ENV_AT_START = "opencode-go/deepseek-v4-pro"
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=50, opencode_go=50)
    env = {
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "BOB_SEAT_MODEL_PIN": "1",
    }
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env, log_fn=logs.append)
    assert got == "opencode/deepseek-v4.1-flash-free"
    assert any("pin:" in line and "free-first" in line for line in logs)


def test_fr8454_resolve_uses_paid_when_free_empty(tmp_path, monkeypatch):
    _isolate_tray(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENCODE_CONFIG", raising=False)
    bw._OPENCODE_MODEL_ENV_AT_START = None
    logs: list[str] = []
    fuel = bw.Fuel(opencode_free=0, opencode_go=40, opencode_models={"deepseek-v4-pro": 40})
    env = {
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "HOME": str(tmp_path),
        "OPENCODE_CONFIG": str(tmp_path / "missing.jsonc"),
    }
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env, log_fn=logs.append)
    assert got is not None
    assert "opencode-go/" in got or got.endswith("-pro")
    assert any(
        "source=paid" in line or "source=fuel" in line or "model=opencode-go/" in line
        for line in logs
    )


def test_fr8454_wrapper_pins_prefer_runtime_and_switch(tmp_path):
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "Do work.", "opencode.exe", tmp_path)
    script = next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))
    assert "$ocFreeModel =" in script
    assert "$ocPaidModel =" in script
    assert "prefer-runtime" in script
    assert "switch-to-paid" in script
    assert "switch-to-free" in script
    # Next Invoke-OpencodeRun reads script scope. A function-local $model is lost.
    assert "$script:model = $prefModel" in script
    assert "$script:model = $to2" in script
    assert "opencode-fuel:" in script
    # hitLimit path still can GIVEUP when switch fails
    assert "Write-OpencodeJobGiveup" in script
    # End-of-turn rebind after turn_ended
    te = script.find("Write-OpencodeTurnMarker 'turn_ended'")
    assert te > 0
    assert script.find("prefer-runtime", te) > te
