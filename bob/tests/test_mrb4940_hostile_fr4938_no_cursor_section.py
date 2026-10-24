"""docs/mrb-4940: hostile pins for FR #4938 TipForm/Status Cursor section removal."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DIALOGS_PS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"


def _rebuild_body() -> str:
    w = WATCH.read_text(encoding="utf-8-sig")
    start = w.index("function Rebuild-BobTrayTiles")
    end = w.index("Atomic swap on the TipForm", start)
    return w[start:end]


def test_rebuild_first_section_header_is_grok_accounts_not_cursor():
    """TipForm must open with Grok accounts; Cursor spending-group header must be gone."""
    sec = _rebuild_body()
    # First painted section title after FR #4938.
    assert "Title 'Grok accounts'" in sec or 'Title "Grok accounts"' in sec
    assert "Title 'Cursor'" not in sec and 'Title "Cursor"' not in sec
    # Overspend (if any) rides the Grok accounts header, not a Cursor header.
    grok_hdr = sec.index("Title 'Grok accounts'") if "Title 'Grok accounts'" in sec else sec.index('Title "Grok accounts"')
    assert "Format-BobTrayCursorOverspendLine" in sec
    assert sec.index("Format-BobTrayCursorOverspendLine") < grok_hdr + 200


def test_status_render_never_sections_cursor_even_if_snapshot_has_rows():
    """BobStatus.cs must not paint a Cursor section (snapshot may still carry cursor[])."""
    src = STATUS_CS.read_text(encoding="utf-8-sig")
    render = src[src.index("public int Render") : src.index("protected override void OnPaint")]
    assert 'Section(g, y, "Cursor"' not in render
    assert "foreach (StatusRow r in m.Cursor)" not in render
    assert 'Section(g, y, "Grok accounts"' in render


def test_status_model_never_fills_cursor_from_hover_pools():
    ps = DIALOGS_PS.read_text(encoding="utf-8-sig")
    fn = ps.split("function New-BobTrayStatusModel", 1)[1].split("\nfunction ", 1)[0]
    assert "cursor_pools" not in fn
    assert "$cursor.Add(" not in fn
    assert "FR #4938" in fn or "FR #4938" in ps[: ps.index("function New-BobTrayStatusModel") + 400]
