"""FR #9264 / BOB-TRAY-UI-04: OpenCode keys on About; no top-level tray menu item."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ABOUT = ROOT / "tray" / "dialogs" / "BobAbout.cs"
TRAY = ROOT / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_fr9264_aboutform_has_opencode_keys_button():
    text = _read(ABOUT)
    about = text[text.index("internal class AboutForm") : text.index("internal static class AboutProgram")]
    assert 'keys.Text = "OpenCode keys"' in about
    assert "openOpencodeKeys" in about
    assert 'keys.Name = "opencodeKeys"' in about
    ctrl = about.split("Controls.AddRange", 1)[1].split(";", 1)[0]
    assert "keys" in ctrl and "logs" in ctrl and "ok" in ctrl
    # Standalone bob-about uses null action overload (button hidden).
    assert "this(root, null)" in about or "AboutForm(string root) : this(root, null)" in about


def test_fr9264_tipform_wires_about_and_drops_top_menu():
    src = _read(TRAY)
    # No top-level OpenCode keys MenuItems inventory.
    build = src
    # The menu construction must not Add OpenCode keys to MenuItems / menu.Items as a top sibling.
    assert 'MenuItems.Add("OpenCode keys")' not in src
    assert "miOcKeys" not in src
    assert "ShowOpencodeKeysFromAbout" in src
    assert "new AboutForm(root, ShowOpencodeKeysFromAbout)" in src
    assert "SeedOpencodeKeyChoices(cms.Items, false)" in src
    # Store + interactive helpers remain.
    assert "SetOpencodeKeyInteractive" in src
    assert "class OpencodeKeysStore" in src


def test_fr9264_ps_about_fallback_has_opencode_keys_button():
    text = _read(WATCH)
    fn = text[text.index("function Show-BobTrayAbout") : text.index("function Close-BobTrayDialogs")]
    assert "$keys.Text = 'OpenCode keys'" in fn
    assert "$keys.Name = 'opencodeKeys'" in fn
    # Top PS strip still has no OpenCode keys sibling (was never present).
    menu_build = text[text.index("$miWeights = $menu.Items.Add('Weights')") : text.index("$notify.ContextMenuStrip = $menu")]
    assert "OpenCode keys" not in menu_build


def test_fr9264_docs_mention_about_opencode_keys():
    text = DOCS.read_text(encoding="utf-8")
    assert "9264" in text
    assert "OpenCode keys" in text
    assert "About" in text
