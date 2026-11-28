"""FR #10313: automatic OpenCode must free-fallthrough when unpinned (regression #10173)."""
from __future__ import annotations

import bob.scripts.bob_worker as bw


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    monkeypatch.delenv("BOB_SEAT_MODEL_PIN", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    bw._OPENCODE_MODEL_ENV_AT_START = None


def test_fr10313_free100_automatic_resolves_free_default(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        '{"workerStartModels":{"opencode":"opencode-go/deepseek-v4-pro"}}',
    )
    fuel = bw.Fuel(opencode_free=100, opencode_go=None)
    env = {
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "BOB_WORKER_START_MODEL_JSON": '{"workerStartModels":{"opencode":"opencode-go/deepseek-v4-pro"}}',
    }
    got = bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env)
    assert got == "opencode/deepseek-v4.1-flash-free"


def test_fr10313_pinned_still_returns_saved_model_only(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    paid = "opencode-go/deepseek-v4-pro"
    bw._OPENCODE_MODEL_ENV_AT_START = paid
    env = {
        "BOB_OPENCODE_MODEL": paid,
        "BOB_SEAT_MODEL_PIN": "1",
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    fuel = bw.Fuel(opencode_free=100, opencode_go=None)
    assert bw.resolve_opencode_model(fuel, state_dir=tmp_path, env=env) == paid


def test_fr10313_refusal_mentions_free_when_unresolved(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    import opencode_fuel as of

    now = 1_800_000_000.0
    of.save_opencode_pauses(tmp_path, {"opencode-free": now + 600})
    fuel = bw.Fuel(opencode_free=100, opencode_go=None)
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(bw, "report_seat_start_refusal", fake_report)
    bw.report_opencode_model_refusal(
        None, machine="redqueen", fuel=fuel, env={"LOCALAPPDATA": str(tmp_path)}
    )
    reason = str(seen.get("reason") or "")
    assert "free=100" in reason
    assert "capped/paused" not in reason.lower() or "paused/capped" in reason.lower()