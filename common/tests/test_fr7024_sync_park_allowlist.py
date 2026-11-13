"""FR #7024: dirty-park must not wipe arbitrary local edits (VISION 020 / #1074).

FR #6989 parks only known hotpatch paths (RecycleSeat / gitclaim / recycleseat).
Overlapping edits on other tracked files still block ff-only and keep the working tree.
"""
from __future__ import annotations

from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"


def test_fr7024_park_allowlist_pins():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Test-BobiverseSyncParkHotpatchPath" in text
    assert "BobTrayRecycleSeat" in text
    assert "gitclaim" in text
    assert "recycleseat" in text
    assert "FR#7024" in text
    assert "skip-not-hotpatch" in text
