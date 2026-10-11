"""FR #3997: weekly Grok first for seat start and Get-BobFuelOrder."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

import bob_worker as bw


def test_fr3997_fuel_order_ps1_starts_with_grok_build():
    text = (ROOT / "tray" / "src" / "Public" / "Get-BobCapacity.ps1").read_text(encoding="utf-8-sig")
    i = text.index("function Get-BobFuelOrder")
    chunk = text[i : i + 500]
    assert "$order = @('grok-build', 'cursor-models')" in chunk
    assert "FR #3997" in chunk


def test_fr3997_select_agent_prefers_grok_when_both_have_fuel():
    d = bw.select_agent(bw.Fuel(40, 10, 50, "available"), r"C:\c\agent.cmd", r"C:\g\agent.exe")
    assert d.kind == "grok"


def test_fr3997_agent_fuel_helper_synopsis_grok_first():
    text = (ROOT / "tray" / "tools" / "Get-BobAgentFuel.ps1").read_text(encoding="utf-8-sig")
    assert "grok -> cursor -> dialog" in text
