"""FR #6147 clarification: TipForm/Status paint Go rolling/weekly/monthly windows."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
MOCK_HOME = ROOT / "docs" / "mocks" / "digest-fuel" / "home.html"
MOCK_EMPTY = ROOT / "docs" / "mocks" / "digest-fuel" / "empty.html"
FR007 = ROOT / "docs" / "fr" / "digest-ear-publish" / "FR-007.md"


def test_format_opencode_window_helpers_exist():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Format-BobOpencodeWindowLine" in src
    assert "function Format-BobOpencodeWindowLines" in src
    assert "not measured" in src
    assert "opencode_windows" in src
    assert "opencode_window_lines" in src
    # BOM-less PS1 must build middle-dot via char code, not a literal.
    assert "[char]0x00B7" in src


def test_watch_and_status_carry_window_lines():
    w = WATCH.read_text(encoding="utf-8-sig")
    assert "OpencodeWindowLines" in w or "opencode_window_lines" in w
    assert "Format-BobOpencodeWindowLines" in w
    dlg = DIALOGS.read_text(encoding="utf-8-sig")
    assert "opencode_window_lines" in dlg
    assert "opencode_windows" in dlg
    cs = STATUS_CS.read_text(encoding="utf-8-sig")
    assert "OpencodeWindowLines" in cs
    render = cs.split("public int Render(Graphics g)", 1)[1].split("protected override", 1)[0]
    assert "OpencodeWindowLines" in render


def test_legacy_free_go_formatter_still_present():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Format-BobOpencodePoolLine" in src
    # FR #7017: Go-only pool line (no free bit).
    assert "OpenCode  go" in src
    assert "opencode-free" in src or "opencode_free" in src


def test_mocks_and_fr007_name_three_go_windows():
    home = MOCK_HOME.read_text(encoding="utf-8")
    empty = MOCK_EMPTY.read_text(encoding="utf-8")
    assert "Starts on first use" in home
    assert "72% used" in home and "28% rem" in home
    assert "36% used" in home and "64% rem" in home
    assert "OpenCode" in empty and "n/a" in empty
    fr = FR007.read_text(encoding="utf-8")
    assert "rolling" in fr and "weekly" in fr and "monthly" in fr
    assert "Starts on first use" in fr


def test_mrb6232_hover_prepends_opencode_block_in_order():
    """MRB #6232: summary + windows prepended as one block (not reverse per-line)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
    text = src.read_text(encoding="utf-8")
    assert "$ocBlock" in text
    assert "foreach ($wl in @($opencodeWindowLines))" in text
    # Must not per-line prepend window rows after summary (old reverse bug).
    assert "foreach ($wl in @($opencodeWindowLines)) { if ($wl) { $jobLines = @(('  {0}' -f $wl)) + $jobLines } }" not in text

