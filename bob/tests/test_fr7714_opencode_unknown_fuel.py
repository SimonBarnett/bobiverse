"""FR #7714: unknown OpenCode fuel retries, then the clicked seat still starts."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

OP = r"C:\o\opencode.exe"
CUR = r"C:\c\agent.cmd"
GRK = r"C:\g\agent.exe"


def test_fr7714_unknown_every_read_starts_after_retries():
    sleeps = []
    reads = {"n": 0}

    def read():
        reads["n"] += 1
        return bw.Fuel()

    logs = []
    fuel = bw.reread_explicit_opencode_fuel(read, logs.append, sleep_fn=sleeps.append)
    assert reads["n"] == 3
    assert sleeps == [10.0, 10.0]
    assert any("fuel unknown, starting" in line for line in logs)
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "opencode"
    assert "fuel unknown, starting" in dec.reason
    assert dec.kind != "grok"


def test_fr7714_known_on_second_read_does_not_wait_further():
    sleeps = []
    fuels = [bw.Fuel(), bw.Fuel(opencode_free=40)]

    def read():
        return fuels.pop(0)

    logs = []
    fuel = bw.reread_explicit_opencode_fuel(read, logs.append, sleep_fn=sleeps.append)
    assert sleeps == [10.0]
    assert fuel.opencode_free == 40
    assert not any("fuel unknown, starting" in line for line in logs)
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=False)
    assert dec.kind == "opencode"


def test_fr7714_known_zero_is_refused_and_kind_stays_opencode_refusal():
    fuel = bw.Fuel(grok_pct=90, grok_state="available", opencode_free=0, opencode_go=0)
    dec = bw.explicit_agent_decision("opencode", fuel, CUR, GRK, OP, auth_present=True)
    assert dec.kind == "refuse"
    assert dec.reason.startswith("explicit opencode: no usable fuel")
