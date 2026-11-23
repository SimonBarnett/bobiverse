"""FR #9170: TipForm menu arm via timestamp (no Enabled=false); left-click dismisses stuck menu."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
EVIDENCE = ROOT / "docs" / "bob-9170-tray-menu-arm-timestamp.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_evidence_doc_names_9170():
    assert EVIDENCE.is_file()
    text = _txt(EVIDENCE)
    assert "FR #9170" in text
    assert "timestamp" in text.lower()
    assert "Enabled=false" in text or "Enabled = false" in text
    assert "StatusMenuDismiss" in text
    assert "Update-Hover" in text


def test_watch_menu_arm_uses_timestamp_not_enabled_false():
    text = _txt(WATCH)
    assert "FR #9170" in text
    assert "menuArmUntilUtc" in text
    assert "menuArmMs" in text
    assert "Add_Opened" in text
    # Must not bulk-disable items on MenuOpened (STA starve = grey dead menu).
    opened = text.split("Add_Opened", 1)[1].split("Add_Closed", 1)[0]
    assert "Enabled = $false" not in opened
    assert "Enabled=$false" not in opened
    assert "menuArmUntilUtc" in opened


def test_watch_exit_ignores_clicks_inside_arm_window():
    text = _txt(WATCH)
    assert "Exit ignored reason=menu-arm-ts" in text
    assert "menuArmUntilUtc" in text
    # Exit click path must gate on the arm timestamp before Invoke-BobTrayExit.
    idx_exit = text.index("$miExit.Add_Click")
    # Include Yes/No confirm (FR #9163) after the arm gate (FR #9170).
    chunk = text[idx_exit : idx_exit + 900]
    assert "menuArmUntilUtc" in chunk
    assert "Invoke-BobTrayExit" in chunk
    assert "menu-arm-ts" in chunk


def test_watch_left_click_status_menu_dismiss_then_card():
    text = _txt(WATCH)
    assert "StatusMenuDismiss" in text
    idx = text.index("$notify.Add_MouseClick")
    # FR #9186 BalloonTip proof sits above StatusMenuDismiss; keep a wider window.
    chunk = text[idx : idx + 1600]
    assert "StatusMenuDismiss" in chunk
    assert "Close()" in chunk or "$menu.Close()" in chunk
    assert "Invoke-BobTrayStatus" in chunk


def test_watch_park_status_skips_update_hover_before_card():
    text = _txt(WATCH)
    # Invoke-BobTrayStatus TipForm fallback must not call Update-Hover (STA starve).
    fn = text.split("function Invoke-BobTrayStatus", 1)[1].split("\nfunction ", 1)[0]
    assert "Show-BobTrayCard" in fn
    # Comments may name Update-Hover; forbid a bare call on its own statement.
    assert "\n    Update-Hover\n" not in fn
    assert "Update-Hover;" not in fn


def test_watch_tip_show_clears_sticky_when_menu_not_visible():
    text = _txt(WATCH)
    assert "menuOpenSticky" in text
    fn = text.split("function Show-BobTrayCard", 1)[1].split("\nfunction ", 1)[0]
    assert "menuOpenSticky" in fn
    assert "Visible" in fn
