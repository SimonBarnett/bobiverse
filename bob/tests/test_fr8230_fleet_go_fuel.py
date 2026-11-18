"""FR #8230: a missing local Go figure uses a fresh fleet reading."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw


def _digest(remaining, *, fresh=True, age_s=30, limited=False, usage="go-zen-usage"):
    now = time.time()
    return {
        "opencode": {
            "opencode-go": {
                "remaining": remaining,
                "fresh": fresh,
                "fetched_at": now - age_s,
                "limited": limited,
                "usage_source": usage,
                "source": "credman:bobiverse/jeeves/opencode-go-key",
            }
        }
    }


def test_fresh_fleet_78_fills_null_go_and_logs_source():
    local = bw.Fuel(opencode_free=100, opencode_go=None)
    fuel, source, age = bw.supplement_fuel_from_fleet(local, _digest(78), now=time.time())
    assert fuel.opencode_go == 78
    assert fuel.opencode_free == 100
    assert source == "fleet:go-zen-usage"
    assert age is not None and age < 60
    line = bw.format_fuel_reading(
        fuel, "opencode", start_model="opencode-go/deepseek-v4-pro", source=source, age_s=age
    )
    assert "pool=opencode_go" in line
    assert "pct=78" in line
    assert "known=True" in line
    assert "exhausted=False" in line
    assert "source=fleet:go-zen-usage" in line
    assert "credman" not in line
    assert bw.fuel_explicitly_exhausted(fuel, "opencode", "opencode-go/deepseek-v4-pro") is False


def test_fleet_limited_or_zero_exhausts_go_only():
    now = time.time()
    limited, src, _age = bw.supplement_fuel_from_fleet(
        bw.Fuel(opencode_free=100, opencode_go=None),
        _digest(None, limited=True),
        now=now,
    )
    assert limited.opencode_go == 0
    assert src.startswith("fleet:")
    assert bw.fuel_explicitly_exhausted(limited, "opencode", "opencode-go/m") is True
    assert bw.fuel_explicitly_exhausted(limited, "opencode", "opencode/free-model") is False
    assert bw.fuel_explicitly_exhausted(limited, "grok") is False
    assert bw.fuel_explicitly_exhausted(limited, "cursor") is False
    zero, _, _ = bw.supplement_fuel_from_fleet(
        bw.Fuel(opencode_go=None), _digest(0), now=now
    )
    assert bw.fuel_explicitly_exhausted(zero, "opencode", "opencode-go/m") is True


def test_stale_or_not_fresh_stays_unknown():
    now = time.time()
    stale, src, _ = bw.supplement_fuel_from_fleet(
        bw.Fuel(opencode_go=None), _digest(78, age_s=601), now=now
    )
    assert stale.opencode_go is None
    assert src == ""
    assert bw.fuel_reading_known(stale, "opencode", "opencode-go/m") is False
    cold, src2, _ = bw.supplement_fuel_from_fleet(
        bw.Fuel(opencode_go=None), _digest(78, fresh=False, age_s=10), now=now
    )
    assert cold.opencode_go is None
    assert src2 == ""
    assert bw.fuel_reading_known(cold, "opencode", "opencode-go/m") is False


def test_midjob_reuses_fleet_reading_without_second_local_call():
    now = time.time()
    calls = {"n": 0}

    def local():
        calls["n"] += 1
        return bw.Fuel(opencode_free=100, opencode_go=None)

    fuel, source, _age, hold = bw.take_midjob_fuel(
        local, _digest(78), now=now, hold=None, pool="opencode_go"
    )
    assert calls["n"] == 1
    assert fuel.opencode_go == 78
    assert source.startswith("fleet:")
    fuel2, source2, _age2, hold2 = bw.take_midjob_fuel(
        local, _digest(1), now=now + 30, hold=hold, pool="opencode_go"
    )
    assert calls["n"] == 1
    assert fuel2.opencode_go == 78
    assert source2.startswith("fleet:")
    assert hold2 is hold


def test_agent_fuel_script_passes_windows_and_limiting():
    text = (
        Path(__file__).resolve().parents[1] / "tray" / "tools" / "Get-BobAgentFuel.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "$out.opencode.windows" in text
    assert "$out.opencode.limiting" in text
    assert "/zen/go/" not in text
