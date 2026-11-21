"""FR #8540: free=0 + go=None with no start model must not refuse as exhausted."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

OP = r"C:\o\opencode.exe"
CUR = r"C:\c\agent.cmd"
GRK = r"C:\g\agent.exe"


def test_fr8540_free0_go_none_no_model_starts_unknown():
    # Intake: model=unknown pool=opencode free=0 go=None refused incorrectly.
    fuel = bw.Fuel(
        opencode_free=0,
        opencode_go=None,
        grok_pct=3,
        grok_state="available",
    )
    assert bw.seat_fuel_pool("opencode", "") == "opencode"
    assert bw.fuel_reading_known(fuel, "opencode") is False
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "opencode"
    assert "fuel unknown" in dec.reason.lower() or "go unknown" in dec.reason.lower() or "starting" in dec.reason.lower()
    assert dec.kind != "refuse"


def test_fr8540_free0_go0_still_refuses():
    fuel = bw.Fuel(opencode_free=0, opencode_go=0, grok_pct=3, grok_state="available")
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "refuse"
    assert "no usable fuel" in dec.reason


def test_fr8540_free0_go_none_windows_usable_starts():
    windows = {
        "week": {"remaining_pct": 81, "limited": False},
        "rolling": {"remaining_pct": 94, "limited": False},
        "month": {"remaining_pct": 91, "limited": False},
    }
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, opencode_windows=windows)
    assert bw.fuel_reading_known(fuel, "opencode") is True
    assert bw.opencode_has_tokens(fuel) is True
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "opencode"
    assert dec.kind != "refuse"


def test_fr8540_free100_go_none_still_known():
    # FR #8158: free positive alone keeps either-pool known for selection.
    fuel = bw.Fuel(opencode_free=100, opencode_go=None)
    assert bw.fuel_reading_known(fuel, "opencode") is True
    assert bw.opencode_has_tokens(fuel) is True