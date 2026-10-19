"""FR #4802: Cursor/Sand usagePercent is percentage points (0-100), never a 0-1 fraction.

A real 0.99% used must stay ~1% used (99% remaining), not rescale to 99% used.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
USAGE_PY = ROOT / "tray" / "tools" / "Get-CursorAgentUsage.py"
HOVER_PS1 = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def _load_usage():
    assert USAGE_PY.is_file(), USAGE_PY
    spec = importlib.util.spec_from_file_location("cursor_agent_usage_fr4802", USAGE_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "raw,used,remain",
    [
        (0, 0, 100),
        (0.5, 0, 100),  # round(0.5)=0 used? round half even in py3 - 0.5 -> 0 or 1?
        (0.99, 1, 99),
        (1, 1, 99),
        (1.5, 2, 98),
        (57.39, 57, 43),
        (100, 100, 0),
        ("0.99", 1, 99),
        ("57.39", 57, 43),
    ],
)
def test_fr4802_parse_used_remain_is_percentage_points(raw, used, remain):
    mod = _load_usage()
    got_used, got_remain = mod._parse_used_remain(raw)
    assert got_used == used, (raw, got_used, used)
    assert got_remain == remain, (raw, got_remain, remain)


def test_fr4802_parse_used_remain_matches_pct_points_helper():
    """Sand path must not diverge from planUsage percentage-point parsing."""
    mod = _load_usage()
    for raw in (0, 0.5, 0.99, 1, 1.5, 57.39, 100, None, ""):
        assert mod._parse_used_remain(raw) == mod._parse_pct_points(raw)


def test_fr4802_build_spending_groups_sand_0_99_not_99_used():
    mod = _load_usage()
    groups = mod.build_spending_groups(
        period={"planUsage": {"apiPercentUsed": 10, "autoPercentUsed": 20}},
        sand={"usagePercent": 0.99},
    )
    by_id = {g["id"]: g for g in groups}
    assert by_id["grok-chat"]["used_pct"] == 1
    assert by_id["grok-chat"]["remaining_pct"] == 99
    # planUsage fields already percentage points
    assert by_id["high-cost-models"]["used_pct"] == 10
    assert by_id["auto"]["used_pct"] == 20


def test_fr4802_python_source_no_fraction_rescale():
    text = USAGE_PY.read_text(encoding="utf-8")
    # Old bug: if 0.0 <= used_f <= 1.0: used_f *= 100.0
    assert "used_f *= 100" not in text
    assert "used_f *= 100.0" not in text
    assert "FR #4802" in text


def test_fr4802_powershell_sand_pct_no_fraction_rescale():
    text = HOVER_PS1.read_text(encoding="utf-8")
    assert "function ConvertTo-BobCursorSandPct" in text
    # Old bug: if ($usedF -ge 0.0 -and $usedF -le 1.0) { $usedF = $usedF * 100.0 }
    assert "* 100.0" not in text.split("function ConvertTo-BobCursorSandPct", 1)[1].split(
        "function Get-BobCursorSpendingFromApiFixture", 1
    )[0]
    assert "FR #4802" in text
