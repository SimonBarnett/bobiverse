"""FR #4938: after account unification, TipForm / Status must not show Cursor pool bars.

Per-machine Grok account rows stay. Fleet Cursor spending groups (grok chat / high cost /
Low cost models) are obsolete UI - one grok/cursor account per machine.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS_PS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"


def test_rebuild_tiles_has_no_cursor_section_header():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Title 'Cursor'" not in sec and 'Title "Cursor"' not in sec
    # FR #5032: no "Grok accounts" heading either --- every row is a Grok pool.
    assert "Title 'Grok accounts'" not in sec and 'Title "Grok accounts"' not in sec
    # Must not still paint pool rows from spending-group headings.
    assert "foreach ($pool in $pools)" not in sec
    assert "Get-BobTrayCursorGroupHelpTooltip" not in sec


def test_status_model_does_not_emit_cursor_pool_rows():
    ps = DIALOGS_PS.read_text(encoding="utf-8-sig")
    fn = ps.split("function New-BobTrayStatusModel", 1)[1].split("\nfunction ", 1)[0]
    # Cursor list stays empty for the Status card (FR #4938); Grok rows still built.
    assert "$cursor.Add($row)" not in fn
    assert "cursor_pools" not in fn
    assert "$grok.Add($row)" in fn


def test_status_cs_skips_cursor_section_when_drawing():
    src = STATUS_CS.read_text(encoding="utf-8-sig")
    render = src[src.index("public int Render") : src.index("protected override void OnPaint")]
    assert 'Section(g, y, "Cursor"' not in render
    # FR #5032: no "Grok accounts" Section heading.
    assert 'Section(g, y, "Grok accounts"' not in render
    assert "foreach (StatusRow r in m.Grok)" in render


def test_docs_no_longer_say_cursor_pools_first():
    d = DOCS.read_text(encoding="utf-8-sig")
    assert "Cursor pools first" not in d
    assert "FR #4938" in d or "no Cursor" in d
