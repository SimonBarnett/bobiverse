"""FR #5172: TipForm shows one Copilot pool line (not per machine)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_format_copilot_pool_line_exists():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Format-BobCopilotPoolLine" in src
    assert "unlimited, {0} used" in src
    assert "Copilot  unknown" in src
    assert "Copilot  exhausted" in src
    assert "copilot_pool" in src
    assert "copilot_line" in src


def test_rebuild_tiles_one_copilot_row():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Format-BobCopilotPoolLine" in sec
    assert "CopilotPool" in sec
    assert sec.count("Format-BobCopilotPoolLine") == 1
