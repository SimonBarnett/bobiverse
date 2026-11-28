"""FR #8454: start free unless free is known 0; then the paid tray slot."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

FREE = "opencode/deepseek-v4.1-flash-free"
PAID = "opencode-go/deepseek-v4-pro"
OTHER_FREE = "opencode/beam-free"


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    monkeypatch.delenv("BOB_SEAT_MODEL_PIN", raising=False)
    monkeypatch.delenv("OPENCODE_CONFIG", raising=False)


def test_paid_pin_is_the_opened_weight(tmp_path, monkeypatch):
    """A paid model chosen at seat open is the weight. Free-first does not replace it."""
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = PAID
    env = {"BOB_OPENCODE_MODEL": PAID, "BOB_SEAT_MODEL_PIN": "1", "LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}
    logs: list[str] = []
    got = bw.resolve_opencode_model(bw.Fuel(), state_dir=tmp_path, env=env, log_fn=logs.append)
    assert got == PAID
    assert any("source=env" in line for line in logs)


def test_free_zero_paid_positive_starts_paid_slot(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = FREE
    env = {"BOB_OPENCODE_MODEL": FREE, "BOB_SEAT_MODEL_PIN": "1", "LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}
    fuel = bw.Fuel(opencode_free=0, opencode_go=40)
    logs: list[str] = []
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env, log_fn=logs.append)
    assert got == FREE
    assert any("source=env" in line for line in logs)


def _pause_free_pool(state_dir, now):
    import opencode_fuel as of

    assert of.save_opencode_pauses(state_dir, {"opencode-free": now + 600})


def test_free_catalogue_positive_but_pool_paused_starts_paid(tmp_path, monkeypatch):
    """FR #8555: a free reading of 100 must not hide an active free-pool pause."""
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = FREE
    now = 1_800_000_000.0
    _pause_free_pool(tmp_path, now)
    env = {
        "BOB_OPENCODE_MODEL": FREE,
        "BOB_SEAT_MODEL_PIN": "1",
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    fuel = bw.Fuel(opencode_free=100, opencode_go=40)
    logs: list[str] = []
    got = bw.resolve_opencode_model(
        fuel, state_dir=tmp_path, now=now, env=env, log_fn=logs.append
    )
    assert got == FREE


def test_free_catalogue_positive_pool_paused_go_zero_returns_none(tmp_path, monkeypatch):
    """FR #8555: paused free + known-zero Go leaves no candidate (no model=- crash)."""
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = FREE
    now = 1_800_000_000.0
    _pause_free_pool(tmp_path, now)
    env = {
        "BOB_OPENCODE_MODEL": FREE,
        "BOB_SEAT_MODEL_PIN": "1",
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    fuel = bw.Fuel(opencode_free=100, opencode_go=0)
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, now=now, env=env)
    assert got == FREE


def test_both_exhausted_returns_none(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bw._OPENCODE_MODEL_ENV_AT_START = None
    fuel = bw.Fuel(opencode_free=0, opencode_go=0)
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env={"LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)})
    assert got is None


def test_tray_paid_slot_not_a_third_model(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        '{"models":{"opencodeFree":"%s","opencodePaid":"opencode-go/kimi-k3"}}' % OTHER_FREE,
    )
    bw._OPENCODE_MODEL_ENV_AT_START = PAID
    fuel = bw.Fuel(opencode_free=0, opencode_go=10, opencode_models={"glm-5.3": 9, "kimi-k3": 8})
    got = bw.resolve_opencode_model(
        fuel,
        state_dir=tmp_path,
        env={
            "LOCALAPPDATA": str(tmp_path),
            "XDG_CONFIG_HOME": str(tmp_path),
            "BOB_WORKER_START_MODEL_JSON": '{"models":{"opencodeFree":"%s","opencodePaid":"opencode-go/kimi-k3"}}' % OTHER_FREE,
            "BOB_OPENCODE_MODEL": PAID,
            "BOB_SEAT_MODEL_PIN": "1",
        },
    )
    assert got == PAID


def test_wrapper_switches_to_paid_without_dropping_ceiling_giveup(tmp_path):
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "prompt", "opencode.exe", tmp_path)
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "function Try-OpencodeSwitchToPaid" in script
    assert "return $false" in script
    assert "opencode switch-to-paid model=" not in script
    assert "hard ceiling" in script
    assert "Write-OpencodeJobGiveup $jobKey $killReason" in script
    assert "$timedOut" in script
    assert PAID in script
    # Ceiling path still gives up; it must not call the paid switch.
    ceil = script.split("hard ceiling", 1)[1][:800]
    assert "Try-OpencodeSwitchToPaid" not in ceil
    assert "Write-OpencodeTurnMarker 'turn_ended'" in script


def test_hitlimit_does_not_giveup_after_live_paid_switch(tmp_path):
    """A live switch sets ocPaidSwitched. The later hitLimit block must not GIVEUP."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "prompt", "opencode.exe", tmp_path)
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    hit = script.find("if ($hitLimit)")
    assert hit > 0
    window = script[hit:hit + 2200]
    assert "ocPaidSwitched" in window
    assert "if ($jobKey -and -not $script:ocPaidSwitched)" in window
