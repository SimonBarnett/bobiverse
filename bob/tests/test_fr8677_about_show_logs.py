"""FR #8677 / BOB-09: About form Show logs button opens tray log."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ABOUT = ROOT / "tray" / "dialogs" / "BobAbout.cs"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def _read(path: Path) -> str:
    # Dialog sources ship UTF-8 with BOM (csc / existing tray convention).
    return path.read_text(encoding="utf-8-sig")


def test_fr8677_aboutform_has_show_logs_button_opening_tray_log():
    text = _read(ABOUT)
    about = text[text.index("internal class AboutForm") : text.index("internal static class AboutProgram")]
    assert 'logs.Text = "Show logs"' in about
    assert 'ok.Text = "Close"' in about
    assert "watch_bob_tray.log" in about
    assert "notepad.exe" in about
    ctrl = about.split("Controls.AddRange", 1)[1].split(";", 1)[0]
    assert "logs" in ctrl and "ok" in ctrl


def test_fr8677_ps_about_fallback_has_show_logs():
    text = _read(WATCH)
    fn = text[text.index("function Show-BobTrayAbout") : text.index("function Close-BobTrayDialogs")]
    assert "$logs.Text = 'Show logs'" in fn
    assert "notepad.exe" in fn
    assert ("watch_bob_tray.log" in fn) or ("$logPath" in fn)
