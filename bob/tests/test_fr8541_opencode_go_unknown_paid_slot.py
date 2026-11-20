"""FR #8541: free=0 + go=None must still pick the paid tray slot (not capped/paused)."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

PAID = "opencode-go/deepseek-v4-pro"


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_WORKER_START_MODEL_FILE", raising=False)
    monkeypatch.delenv("BOB_WORKER_START_MODEL_JSON", raising=False)
    monkeypatch.delenv("BOB_SEAT_MODEL_PIN", raising=False)
    monkeypatch.delenv("OPENCODE_CONFIG", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    bw._OPENCODE_MODEL_ENV_AT_START = None


def test_fr8541_free0_go_none_resolves_paid_slot(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, grok_pct=3, grok_state="available")
    logs: list[str] = []
    got = bw.resolve_opencode_model(
        fuel,
        state_dir=tmp_path,
        env={"LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)},
        log_fn=logs.append,
    )
    assert got == PAID
    assert any("source=paid" in line for line in logs)


def test_fr8541_free0_go0_still_none(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    fuel = bw.Fuel(opencode_free=0, opencode_go=0)
    got = bw.resolve_opencode_model(
        fuel,
        state_dir=tmp_path,
        env={"LOCALAPPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)},
    )
    assert got is None


def test_fr8541_refusal_reason_names_go_unknown(monkeypatch):
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(bw, "report_seat_start_refusal", fake_report)
    fuel = bw.Fuel(opencode_free=0, opencode_go=None)
    bw.report_opencode_model_refusal(None, machine="flamingo", fuel=fuel, env={})
    reason = str(seen.get("reason") or "").lower()
    assert "go fuel unknown" in reason
    assert "not capped/paused" in reason
    assert reason.strip() != "opencode: no usable model (capped/paused)"