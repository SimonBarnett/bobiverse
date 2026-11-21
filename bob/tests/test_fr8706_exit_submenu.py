"""FR #8706 / BOB-07: Exit submenu hosts Reload, Restart engine, Exit."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-07-exit-submenu-evidence.md"


def _cs() -> str:
    return TRAY.read_text(encoding="utf-8-sig")


def test_evidence():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-07" in text
    assert "Exit" in text
    assert "Reload" in text
    assert "Restart engine" in text


def test_exit_submenu_in_bob_tray_cs():
    src = _cs()
    # Parent Exit submenu (not three top-level Item calls for these actions).
    assert 'new ToolStripMenuItem("Exit")' in src
    assert 'DropDownItems.Add' in src
    # Children under Exit only, BOB-07 labels.
    assert '"Reload"' in src
    assert '"Restart engine"' in src
    # Must not keep prior top-level Item(...) for these three (Item helper, not ToolStripMenuItem).
    stripped = src.replace('ToolStripMenuItem("Exit")', '')
    assert 'Item("Restart"' not in stripped
    assert 'Item("Reload engine"' not in stripped
    assert 'Item("Exit"' not in stripped
    # Order: Reload, Restart engine, then Exit leaf under the Exit parent.
    i_exit = src.index('new ToolStripMenuItem("Exit")')
    chunk = src[i_exit : i_exit + 1200]
    assert chunk.index('"Reload"') < chunk.index('"Restart engine"')
    # Leaf Exit click still calls ExitTray
    assert "ExitTray" in chunk
    assert "ReloadEngine" in chunk
    assert "Restart()" in chunk or "Restart(" in chunk


def test_tipform_exit_submenu_in_watch_bob_tray():
    text = WATCH.read_text(encoding="utf-8")
    # TipForm also nests under Exit (same S1 surface).
    assert "Reload" in text
    assert "Restart engine" in text
    assert "DropDownItems" in text or ".DropDown" in text
    # No top-level Restart/Exit Add after separator without Exit parent.
    assert ".Items.Add('Restart')" not in text
