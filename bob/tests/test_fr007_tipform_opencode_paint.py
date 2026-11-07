"""FR #6147 / FR-007: TipForm/Status paint OpenCode free/go (n/a when unknown)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
MOCK_HOME = ROOT / "docs" / "mocks" / "digest-fuel" / "home.html"
MOCK_EMPTY = ROOT / "docs" / "mocks" / "digest-fuel" / "empty.html"
CANON_KEYS = ("opencode-free", "opencode-go")


def test_format_opencode_pool_line_exists_and_na():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Format-BobOpencodePoolLine" in src
    assert "OpenCode  n/a" in src
    assert "opencode-free" in src or "opencode_free" in src
    assert "opencode-go" in src or "opencode_go" in src
    # Known values use free/go percent labels (mock: free 100% | go 50%).
    assert "free" in src and "go" in src
    assert "FR #6147" in src or "FR-007" in src


def test_hover_and_status_model_carry_opencode_line():
    hover = HOVER.read_text(encoding="utf-8-sig")
    assert "opencode_line" in hover
    assert "Format-BobOpencodePoolLine" in hover
    dlg = DIALOGS.read_text(encoding="utf-8-sig")
    model = dlg[dlg.index("function New-BobTrayStatusModel") : dlg.index("function Write-BobTrayStatusSnapshot")]
    assert "opencode_line" in model
    assert "opencode_free" in model or "opencode_go" in model


def test_rebuild_tiles_paints_one_opencode_row():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Format-BobOpencodePoolLine" in sec or "OpencodeLine" in sec or "opencode_line" in sec
    assert "OpenCode" in sec or "Opencode" in sec


def test_bobstatus_cs_renders_opencode_line():
    src = STATUS_CS.read_text(encoding="utf-8-sig")
    assert 'Common.Str(d, "opencode_line")' in src or 'Common.Str(d, "opencodeLine")' in src
    assert "OpencodeLine" in src or "OpenCodeLine" in src
    render = src.split("public int Render(Graphics g)", 1)[1].split("protected override", 1)[0]
    assert "OpencodeLine" in render or "OpenCodeLine" in render
    check = src[src.index('--check') : src.index("if (!Common.Single")]
    assert "OpencodeLine" in check or "OpenCodeLine" in check or "opencode" in check.lower()


def test_mocks_align_opencode_free_go():
    home = MOCK_HOME.read_text(encoding="utf-8")
    empty = MOCK_EMPTY.read_text(encoding="utf-8")
    assert "OpenCode" in home
    assert "free 100%" in home
    # FR #6147 clarification mock: limiting weekly remaining + used/rem window lines.
    assert "go weekly 28%" in home or "28% rem" in home
    assert "Starts on first use" in home
    assert "OpenCode" in empty
    assert "n/a" in empty
