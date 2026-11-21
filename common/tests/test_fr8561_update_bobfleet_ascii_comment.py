"""FIX #8561: Update-BobFleet.ps1 tip pin stays BOM-less ASCII (pytest-ascii-bom).

Comment-only U+2014 -> ASCII hyphen on the open tip so CI is not red when main
also fails the same gate (MRB ascii-bom playbook).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Update-BobFleet.ps1"


def test_update_bobfleet_ps1_is_bomless_ascii():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM not allowed"
    # Fail on common non-ASCII that pytest-ascii-bom rejects (em dash, etc.).
    bad = [b for b in raw if b > 127]
    assert not bad, f"non-ASCII bytes in Update-BobFleet.ps1: {bad[:20]!r}"
