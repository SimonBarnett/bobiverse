"""docs/mrb-6684: hostile pins for FR #6664/#6665/#6666 / PR #6684.

Peer meter age is xai_weekly.fetched_at / sampleStale (FR #6285), not
digest-lastSeen-stale. digespcent grok-build cite is FR #6285 / #5047.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HOVER = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
T5032 = ROOT / "bob" / "tests" / "test_fr5032_stale_peer_digest_fuel.py"
T5047 = ROOT / "bob" / "tests" / "test_fr5047_pecache_digespcent_fuel_stale.py"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb6684_expand_uses_sampleStale_not_digest_lastSeen_stale():
    h = _txt(HOVER)
    expand = h[h.index("function Expand-BobReportDigestView") :]
    assert "fetched_at" in expand
    assert "sampleStale" in expand
    assert "$fuelStaleBy[$mac] = $true" in expand or "fuelStaleBy[$mac] = $true" in expand
    assert "digest-lastSeen-stale" not in h


def test_mrb6684_peer_weekly_block_ages_by_measureAt():
    h = _txt(HOVER)
    start = h.index("FR #5032: peer weekly older than the fuel-stale window")
    block = h[start : start + 3500]
    assert "measureAt" in block
    assert "-not $measureAt" in block or "not $measureAt" in block
    assert "fetched_at" in block
    assert "$isPeer" in block or "isPeer" in block


def test_mrb6684_digespcent_loop_cites_6285_5047_and_skips_paint():
    h = _txt(HOVER)
    start = h.index("foreach ($pc in @($digestPcentRows))")
    end = h.find("\n    # HTTP digest machine.weekly", start)
    assert end > start
    block = h[start:end]
    assert "#5047" in block
    assert "6285" in block
    assert "never paint" in block.lower() or "xai_weekly" in block
    assert "continue" in block
    # Contiguous bare ``FR #5047`` alone is not required in this loop.
    assert "FR #5047" not in block or "FR #6285 / #5047" in block


def test_mrb6684_product_pins_drop_digest_lastSeen_stale_assert():
    t = _txt(T5032)
    assert "digest-lastSeen-stale" not in t or "retired" in t.lower()
    assert "sampleStale" in t
    assert "measureAt" in t
    t2 = _txt(T5047)
    assert 'find("\\n    # HTTP digest machine.weekly"' in t2 or "HTTP digest machine.weekly" in t2
    assert "6285" in t2
