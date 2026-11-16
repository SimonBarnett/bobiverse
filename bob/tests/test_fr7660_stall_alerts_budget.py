"""FR #7660: stall-alerts must not force-reload BobBridge inside the timed job."""
from __future__ import annotations

from pathlib import Path

WATCH = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr7660_stall_alerts_uses_warm_runspace_and_45s():
    w = WATCH.read_text(encoding="utf-8")
    i = w.index("Invoke-BobTrayWarmEngineStep -Name 'stall-alerts'")
    chunk = w[i : i + 700]
    assert "Import-Module" not in chunk
    assert "BobTrayEngineStepTimeoutSec" in chunk
    assert "-TimeoutSec 90" not in chunk
    assert "Get-BobStallAlerts" in chunk
    assert "Get-BobTrayWarmEngineShell" in w
