"""FR #8888: stall-alerts must not use an unbounded Win32_Process query."""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "tray" / "src" / "Private" / "Get-BobStallAlerts.ps1"


def test_fr8888_stall_alerts_bounds_win32_process():
    text = SRC.read_text(encoding="utf-8-sig")
    assert "function Get-BobWin32ProcessRows" in text
    assert "EnumerationOptions" in text
    assert "Get-CimInstance" not in text
    assert "Get-BobWin32ProcessRows -TimeoutSec 8" in text
