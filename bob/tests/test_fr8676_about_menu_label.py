"""FR #8676 / BOB-08: tray menu label Acknowledge -> About."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
MOCK = ROOT / "docs" / "mocks" / "systray-agents-workers" / "home.html"


def _utf8(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr8676_bobtray_menu_item_is_about_not_acknowledge():
    text = _utf8(TRAY_CS)
    assert 'Item("About", delegate { Acknowledge(); ShowAbout(); });' in text
    assert 'Item("Acknowledge",' not in text


def test_fr8676_watch_fallback_menu_add_about():
    text = _utf8(WATCH)
    assert "$menu.Items.Add('About')" in text
    assert "$menu.Items.Add('Acknowledge')" not in text


def test_fr8676_mock_home_shows_about():
    html = _utf8(MOCK)
    assert ">About<" in html
    assert "Acknowledge" not in html
