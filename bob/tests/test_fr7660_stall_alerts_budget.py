"""FR #7660: stall-alerts must not force-reload BobBridge inside the timed job."""
from __future__ import annotations

from pathlib import Path

WATCH = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr7660_stall_alerts_skips_forced_import_and_uses_90s():
    w = WATCH.read_text(encoding="utf-8")
    i = w.index("Invoke-BobTrayEngineStep -Name 'stall-alerts'")
    chunk = w[i : i + 700]
    assert "Import-Module $psd1 -Force" not in chunk
    assert "Import-Module $psd1" in chunk
    assert "-TimeoutSec 90" in chunk
    assert "Get-BobStallAlerts" in chunk
