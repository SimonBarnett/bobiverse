"""FR #7659: update-hover-engine must not cold-reload the tray module every poll."""
from __future__ import annotations

from pathlib import Path

WATCH = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"


def _engine_hover() -> str:
    w = WATCH.read_text(encoding="utf-8")
    i = w.index("Invoke-BobTrayWarmEngineStep -Name 'update-hover-engine'")
    return w[i : i + 900]


def test_fr7659_hover_engine_skips_dialogs_and_forced_import():
    chunk = _engine_hover()
    assert "BobTrayDialogs.ps1" not in chunk
    assert "Import-Module" not in chunk
    assert "Invoke-BobTrayWarmEngineStep" in chunk
    assert "BobTrayEngineStepTimeoutSec" in chunk
    assert "-TimeoutSec 90" not in chunk


def test_fr7659_timeout_report_is_rate_limited():
    w = WATCH.read_text(encoding="utf-8")
    start = w.index("function Invoke-BobTrayEngineReportTimeout")
    chunk = w[start : start + 900]
    assert "BobTrayEngineTimeoutReportedAt" in chunk
    assert "TotalMinutes -lt 60" in chunk
