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


def test_compiled_card_renders_copilot_and_engine_writes_before_skip_ui():
    src = (ROOT / "tray" / "dialogs" / "BobStatus.cs").read_text(encoding="utf-8-sig")
    assert 'Common.Str(d, "copilot_line")' in src
    render = src.split("public int Render(Graphics g)", 1)[1].split("protected override", 1)[0]
    assert render.count('Section(g, y, m.CopilotLine, "")') == 1
    w = WATCH.read_text(encoding="utf-8-sig")
    update = w.split("function Update-Hover", 1)[1]
    assert update.index("New-BobTrayStatusModel -Hover $h") < update.index("if ($SkipUi) { return }")
    assert update.index("Write-BobTrayStatusSnapshot -Root") < update.index("if ($SkipUi) { return }")
