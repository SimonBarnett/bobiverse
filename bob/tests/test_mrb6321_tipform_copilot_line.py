"""MRB #6321: TipForm must paint hover Copilot line (Format-* is module-private)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PSD1 = ROOT / "tray" / "src" / "BobBridge.psd1"


def test_mrb6321_rebuild_accepts_copilot_line_from_hover():
    w = WATCH.read_text(encoding="utf-8")
    assert "$CopilotBarPct" in w
    assert "$copilotLine = [string]$CopilotLine" in w
    assert "-CopilotLine ([string]$h.copilot_line)" in w
    assert "-CopilotBarPct $copilotBarPct" in w
    assert "-OpencodeLine $h.opencode_line" in w


def test_mrb6321_format_helpers_not_exported():
    """Regression pin: helpers stay private; TipForm must not require them exported."""
    text = PSD1.read_text(encoding="utf-8")
    assert "Format-BobCopilotPoolLine" not in text
    assert "Get-BobCopilotMeterBarPct" not in text
    assert "Get-BobTrayHover" in text
    hover = HOVER.read_text(encoding="utf-8")
    assert "function Format-BobCopilotPoolLine" in hover
    assert "copilot_line" in hover
    assert "copilot_bar" in hover
