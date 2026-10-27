"""FR #5047: peCache / digespcent peer weekly without fresh lastSeen must not paint live %."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def _txt(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_fr5047_digespcent_grok_build_does_not_fill_peer_weekly():
    h = _txt(HOVER)
    start = h.index("foreach ($pc in @($digestPcentRows))")
    block = h[start : start + 1200]
    assert "FR #5047" in block
    assert "grok-build" in block
    # Peers must not take digespcent weekly (no lastSeen on pcent rows).
    assert "$mac -ne $machineId" in block
    assert "continue" in block


def test_fr5047_pecache_peer_without_lastseen_sets_fuel_stale():
    h = _txt(HOVER)
    start = h.index("FR #5032: durable cache must not resurrect a stale peer")
    block = h[start : start + 2200]
    assert "FR #5047" in block
    assert "fuelStaleBy[$mid2] = $true" in block
    assert "seenBy.ContainsKey($mid2)" in block
    assert "no lastSeen" in block or "without lastSeen" in block or "missing lastSeen" in block
