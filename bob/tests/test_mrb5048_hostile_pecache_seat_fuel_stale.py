"""MRB #5048 hostile: seat peCache peer weekly without fresh lastSeen is fuel_stale."""
from __future__ import annotations

from pathlib import Path

HOVER = Path(__file__).resolve().parents[1] / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_mrb5048_seat_pecache_peer_without_lastseen_sets_fuel_stale():
    h = HOVER.read_text(encoding="utf-8-sig")
    # Two seat peCache weekly fill sites share the FR #5047 peer gate.
    assert h.count("FR #5047: seat peCache weekly must not paint peers without fresh lastSeen.") >= 2
    assert "if (-not $seenBy.ContainsKey($smid)) { $fuelStaleBy[$smid] = $true; continue }" in h


def test_mrb5048_seat_pecache_peer_gate_skips_weeklyby_on_stale_age():
    h = HOVER.read_text(encoding="utf-8-sig")
    # Both seat-week fill loops must refuse aged lastSeen (same fuelStaleAfter as digest).
    assert h.count("$seatAge") >= 1
    assert h.count("$seatAge2") >= 1
    assert h.count("$fuelStaleBy[$smid] = $true") >= 3
    assert h.count("$weeklyBy[$smid] = [int]$seatWeek") >= 2
    # weeklyBy assignment must sit after the peer continue (not before the gate).
    first = h.index("FR #5047: seat peCache weekly must not paint peers without fresh lastSeen.")
    second = h.index(
        "FR #5047: seat peCache weekly must not paint peers without fresh lastSeen.",
        first + 10,
    )
    for start in (first, second):
        block = h[start : start + 900]
        stale = block.index("$fuelStaleBy[$smid] = $true")
        paint = block.index("$weeklyBy[$smid] = [int]$seatWeek")
        assert stale < paint
        assert "continue" in block[stale:paint]
