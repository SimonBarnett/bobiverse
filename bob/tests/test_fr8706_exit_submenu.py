"""FR #8706 / BOB-07: Exit submenu hosts Restart / Reload Engine / --- / Exit."""
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
    assert "Restart" in text
    assert "Reload Engine" in text


def test_exit_submenu_in_bob_tray_cs():
    src = _cs()
    assert 'new ToolStripMenuItem("Exit")' in src
    assert "DropDownItems.Add" in src
    assert '"Restart"' in src
    assert '"Reload Engine"' in src
    # Must not keep prior top-level Item(...) for lifecycle leaves.
    # Top-level Item(...) helper must not wire lifecycle leaves (DropDown ToolStripMenuItem is ok).
    assert 'Item("Restart"' not in src.replace('ToolStripMenuItem("Restart")', '')
    assert 'Item("Reload engine"' not in src
    assert 'Item("Reload Engine"' not in src.replace('ToolStripMenuItem("Reload Engine")', '')
    assert 'Item("Exit"' not in src.replace('ToolStripMenuItem("Exit")', '')
    i_exit = src.index('new ToolStripMenuItem("Exit")')
    chunk = src[i_exit : i_exit + 1600]
    assert chunk.index('"Restart"') < chunk.index('"Reload Engine"')
    assert "new ToolStripSeparator()" in chunk
    assert "ExitTray" in chunk
    assert "ReloadEngine" in chunk
    assert "Restart()" in chunk or "Restart(" in chunk
    # Handler mapping: Restart -> Restart(); Reload Engine -> ReloadEngine()
    assert 'miRestart.Click += delegate { Restart(); }' in chunk
    assert "miReloadEngine.Click += delegate { ReloadEngine(); }" in chunk


def test_tipform_exit_submenu_in_watch_bob_tray():
    text = WATCH.read_text(encoding="utf-8")
    assert "Reload Engine" in text
    assert "ToolStripMenuItem('Restart')" in text
    assert "DropDownItems" in text or ".DropDown" in text
    assert ".Items.Add('Restart')" not in text
    assert "miRestart.Add_Click({ Restart-BobTrayWatcher })" in text
    assert "miReloadEngine.Add_Click" in text
