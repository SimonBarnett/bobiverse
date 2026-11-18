"""FR #8186: seat-start gate judges the pool of the model about to start."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

OP = r"C:\o\opencode.exe"
CUR = r"C:\c\agent.cmd"
GRK = r"C:\g\agent.exe"
GO_MODEL = "opencode-go/deepseek-v4-pro"
FREE_MODEL = "opencode/beam-free"


def test_ac1_go_model_free0_go_none_starts():
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, grok_pct=91, grok_state="available")
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
    )
    assert dec.kind == "opencode"
    assert "pool=opencode_go" in dec.reason or "pool=go" in dec.reason
    assert "unknown" in dec.reason.lower()


def test_ac2_go_model_free0_go81_starts():
    fuel = bw.Fuel(opencode_free=0, opencode_go=81)
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
    )
    assert dec.kind == "opencode"
    assert "refuse" != dec.kind


def test_ac3_go_model_go0_refuses_with_model_and_pool():
    fuel = bw.Fuel(opencode_free=100, opencode_go=0)
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
    )
    assert dec.kind == "refuse"
    assert GO_MODEL in dec.reason
    assert "pool=opencode_go" in dec.reason or "pool=go" in dec.reason


def test_ac3b_per_model_zero_refuses():
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={"deepseek-v4-pro": 0, "glm-5.3": 40},
    )
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
    )
    assert dec.kind == "refuse"
    assert GO_MODEL in dec.reason


def test_ac4_free_model_free0_go81_refuses():
    fuel = bw.Fuel(opencode_free=0, opencode_go=81)
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=FREE_MODEL
    )
    assert dec.kind == "refuse"
    assert FREE_MODEL in dec.reason
    assert "pool=opencode_free" in dec.reason or "pool=free" in dec.reason


def test_ac5_no_model_keeps_either_pool_7714():
    # Unknown both pools -> start (FR #7714).
    fuel = bw.Fuel()
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "opencode"
    assert "fuel unknown" in dec.reason
    # Known free=0 go=0 -> refuse.
    fuel2 = bw.Fuel(opencode_free=0, opencode_go=0)
    dec2 = bw.explicit_agent_decision("opencode", fuel2, CUR, GRK, OP, auth_present=True)
    assert dec2.kind == "refuse"


def test_ac6_go_windows_usable_when_aggregate_null():
    windows = {
        "week": {"remaining_pct": 81, "limited": False},
        "rolling": {"remaining_pct": 94, "limited": False},
        "month": {"remaining_pct": 91, "limited": False},
    }
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, opencode_windows=windows)
    assert bw.seat_fuel_pool("opencode", GO_MODEL) == "opencode_go"
    assert bw.fuel_reading_known(fuel, "opencode", start_model=GO_MODEL) is True
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
    )
    assert dec.kind == "opencode"


def test_ac7_refusal_exit_passes_model(monkeypatch):
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return {"ok": True}

    waits = []

    def fake_wait(**kwargs):
        waits.append(kwargs)
        return None

    monkeypatch.setattr(bw, "report_seat_start_refusal", fake_report)
    monkeypatch.setattr(bw, "wait_refusal_console", fake_wait)
    monkeypatch.setattr(bw, "ensure_console", lambda *a, **k: True)
    dec = bw.Decision("refuse", "explicit opencode: no usable fuel")
    code = bw._explicit_refusal_exit(
        dec,
        lambda *a, **k: None,
        "agent",
        machine="redqueen",
        kind="opencode",
        model=GO_MODEL,
        fuel=bw.Fuel(opencode_free=0, opencode_go=0),
        interactive=True,
    )
    assert code == bw.EXIT_NO_AGENT
    assert seen.get("model") == GO_MODEL
    assert waits and waits[0].get("timeout_s", 0) >= 60


def test_ac8_noninteractive_refusal_does_not_block(monkeypatch):
    waits = []
    monkeypatch.setattr(bw, "report_seat_start_refusal", lambda **k: {"ok": True})
    monkeypatch.setattr(bw, "wait_refusal_console", lambda **k: waits.append(k))
    monkeypatch.setattr(bw, "ensure_console", lambda *a, **k: True)
    dec = bw.Decision("refuse", "explicit opencode: no usable fuel")
    bw._explicit_refusal_exit(
        dec, lambda *a, **k: None, "agent", model=GO_MODEL, interactive=False
    )
    assert waits == [] or waits[0].get("timeout_s", 0) == 0


def test_ac9_unrelated_pool_never_refuses_parametrized():
    # Grok with empty opencode free must still start when grok has fuel.
    fuel = bw.Fuel(grok_pct=50, grok_state="available", opencode_free=0, opencode_go=0)
    assert (
        bw.explicit_agent_decision("grok", fuel, CUR, GRK, OP, auth_present=True).kind
        == "grok"
    )
    # Cursor with empty opencode.
    fuel2 = bw.Fuel(cursor_high=20, cursor_low=10, opencode_free=0, opencode_go=0)
    assert (
        bw.explicit_agent_decision("cursor", fuel2, CUR, GRK, OP, auth_present=True).kind
        == "cursor"
    )
    # OpenCode free model ignores empty go.
    fuel3 = bw.Fuel(opencode_free=40, opencode_go=0)
    assert (
        bw.explicit_agent_decision(
            "opencode", fuel3, CUR, GRK, OP, auth_present=True, start_model=FREE_MODEL
        ).kind
        == "opencode"
    )
    # OpenCode go model ignores empty free.
    fuel4 = bw.Fuel(opencode_free=0, opencode_go=40)
    assert (
        bw.explicit_agent_decision(
            "opencode", fuel4, CUR, GRK, OP, auth_present=True, start_model=GO_MODEL
        ).kind
        == "opencode"
    )


def test_seat_fuel_pool_mapping():
    assert bw.seat_fuel_pool("opencode", GO_MODEL) == "opencode_go"
    assert bw.seat_fuel_pool("opencode", FREE_MODEL) == "opencode_free"
    assert bw.seat_fuel_pool("opencode", "") == "opencode"
    assert bw.seat_fuel_pool("grok") == "grok"
