"""FR #8758: free start model + free=0 must not refuse when paid can still be tried.

Intake on redqueen: model=opencode/deepseek-v4.1-flash-free pool=opencode_free
free=0 go=None refused before resolve_opencode_model free-then-paid (FR #8454 / #8541).
"""
from __future__ import annotations

import bob.scripts.bob_worker as bw

FREE = "opencode/deepseek-v4.1-flash-free"
OP = r"C:\o\opencode.exe"
CUR = r"C:\c\agent.cmd"
GRK = r"C:\g\agent.exe"


def test_fr8758_free_model_free0_go_none_starts_trying_paid():
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, grok_pct=7, grok_state="available")
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=FREE
    )
    assert dec.kind == "opencode"
    assert "trying paid" in dec.reason.lower() or "free exhausted" in dec.reason.lower()
    assert "no usable fuel" not in dec.reason.lower()


def test_fr8758_free_model_free0_go_positive_starts():
    fuel = bw.Fuel(opencode_free=0, opencode_go=40)
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=FREE
    )
    assert dec.kind == "opencode"
    assert "no usable fuel" not in dec.reason.lower()


def test_fr8758_free_model_free0_go0_still_refuses():
    fuel = bw.Fuel(opencode_free=0, opencode_go=0)
    dec = bw.explicit_agent_decision(
        "opencode", fuel, CUR, GRK, OP, auth_present=True, start_model=FREE
    )
    assert dec.kind == "refuse"
    assert "no usable fuel" in dec.reason.lower()


def test_fr8758_resolve_seat_decision_passes_free_start_model():
    fuel = bw.Fuel(opencode_free=0, opencode_go=None)
    bw._OPENCODE_MODEL_ENV_AT_START = FREE
    try:
        dec = bw.resolve_seat_decision(
            "opencode",
            bw.Decision("none", "auto empty"),
            fuel,
            CUR,
            GRK,
            OP,
            auth_present=True,
        )
        assert dec.kind == "opencode"
        assert "no usable fuel" not in dec.reason.lower()
    finally:
        bw._OPENCODE_MODEL_ENV_AT_START = None
