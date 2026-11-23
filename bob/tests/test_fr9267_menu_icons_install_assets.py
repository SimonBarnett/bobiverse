# -*- coding: utf-8 -*-
"""FR #9267 / BOB-TRAY-UI-07: non-Cursor menu icons from reliable install assets.

S1: Grok, OpenCode, Priority, Jeeves, Plan resolve under <install>\\assets\\ (with
repo bob\\tray\\assets\\ fallback). Cursor stays on menu-favicons\\cursor.com.ico.
Loud MISSING log when an asset is absent.
"""
from __future__ import annotations

import struct
from pathlib import Path

from repo_layout import REPO

ASSETS = REPO / "bob" / "tray" / "assets"
TRAY_CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
BUTLER = REPO / "jeeves" / "assets" / "jeeves-butler.ico"
PRIORITY_VENDOR = REPO / "bob" / "vendor" / "priority" / "priority.ico"
PRIORITY_ASSETS = ASSETS / "priority.ico"

REQUIRED_ICOS = (
    ASSETS / "grok-favicon.ico",
    ASSETS / "opencode-favicon.ico",
    ASSETS / "plan-gantt.ico",
    ASSETS / "menu-favicons" / "cursor.com.ico",
    BUTLER,
    PRIORITY_VENDOR,
    PRIORITY_ASSETS,
)


def _assert_real_ico(path: Path) -> None:
    raw = path.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1, path


def test_fr9267_vendored_menu_icons_exist():
    for path in REQUIRED_ICOS:
        assert path.is_file(), f"missing icon asset: {path}"
        _assert_real_ico(path)


def test_fr9267_tipform_prefers_install_assets_for_non_cursor():
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    assert "ResolveTrayMenuIconPath" in cs
    assert 'Path.Combine(rootPath, "assets", name)' in cs
    assert "menu-icon MISSING" in cs
    # Grok / OpenCode must not be install-blind (bob\\tray\\assets only).
    assert 'Path.Combine(root, "bob", "tray", "assets", "grok-favicon.ico")' not in cs
    assert 'Path.Combine(root, "bob", "tray", "assets", "opencode-favicon.ico")' not in cs
    assert "grok-favicon.ico" in cs
    assert "opencode-favicon.ico" in cs
    assert "plan-gantt.ico" in cs
    assert "priority.ico" in cs
    assert "jeeves-butler.ico" in cs
    # Cursor unchanged.
    assert 'Path.Combine(installRoot ?? "", "assets", "menu-favicons", "cursor.com.ico")' in cs


def test_fr9267_watch_tray_parity_and_missing_log():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert r"assets\grok-favicon.ico" in ps
    assert r"assets\opencode-favicon.ico" in ps
    assert r"assets\plan-gantt.ico" in ps
    assert r"assets\priority.ico" in ps or r"vendor\priority\priority.ico" in ps
    assert "menu-favicons\\cursor.com.ico" in ps or r"menu-favicons\cursor.com.ico" in ps
    assert "menu-icon MISSING" in ps
