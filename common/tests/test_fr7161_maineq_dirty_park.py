"""FR #7161: park dirty paths that already equal origin tip so ff-only can proceed."""
from __future__ import annotations

from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "scripts" / "Bobiverse-Common.ps1"


def test_fr7161_maineq_park_helper_present():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Clear-BobiverseMainEqualDirtyForSync" in text
    assert "sync-park-maineq" in text
    assert "FR#7161" in text
    assert "skip-differs-tip" in text
    # Called before ff and again on FR #7008 tip-overlay retry.
    assert text.count("Clear-BobiverseMainEqualDirtyForSync -InstallRoot") >= 2


def test_fr7161_does_not_widen_hotpatch_allowlist():
    """Main-equal park is separate from FR #7024 hotpatch allowlist."""
    text = COMMON.read_text(encoding="utf-8")
    start = text.index("function Test-BobiverseSyncParkHotpatchPath")
    end = text.index("function Clear-BobiverseDirtyTrackedForSync")
    allow = text[start:end]
    assert "BobTrayRecycleSeat" in allow
    assert "Bobiverse-Common.ps1" not in allow
    assert "Sync-BobiverseFromRepo.ps1" not in allow
