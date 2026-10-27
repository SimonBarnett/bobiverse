"""MRB #5048 hostile: seat peCache peer weekly without fresh lastSeen is fuel_stale."""
from __future__ import annotations

from pathlib import Path

HOVER = Path(__file__).resolve().parents[1] / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_mrb5048_seat_pecache_peer_without_lastseen_sets_fuel_stale():
    h = HOVER.read_text(encoding="utf-8-sig")
    # Two seat peCache weekly fill sites share the FR #5047 peer gate.
    assert h.count("FR #5047: seat peCache weekly must not paint peers without fresh lastSeen.") >= 2
    assert "if (-not $seenBy.ContainsKey($smid)) { $fuelStaleBy[$smid] = $true; continue }" in h
