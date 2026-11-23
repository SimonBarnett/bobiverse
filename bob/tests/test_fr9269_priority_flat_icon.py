"""FR #9269 / BOB-TRAY-UI-08: flat Priority click + tray-assets priority.ico."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from repo_layout import REPO

ICO = REPO / "bob" / "tray" / "assets" / "priority.ico"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = REPO / "bob" / "docs" / "bob-54-priority-icon.md"
# Source-of-truth hash for priority-mcp launcher/priority.ico (PRI-07 / BOB-54).
LAUNCHER_SHA256 = "9b580a71378a541d5ba7f3b1c4c6682b5b915360bb2d070902159e9364dc5bad"


def test_fr9269_priority_asset_is_launcher_ico():
    assert ICO.is_file()
    raw = ICO.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1
    assert hashlib.sha256(raw).hexdigest() == LAUNCHER_SHA256


def test_fr9269_tipform_flat_priority_no_submenu():
    cs = TRAY.read_text(encoding="utf-8-sig")
    assert 'MenuItems.Add("Start PriorityAgent")' not in cs
    assert 'MenuItems.Add("Configure MCP (mcp.ntsa.uk)")' not in cs
    assert "miPriorityStart" not in cs
    assert "miPriority.DropDownItems" not in cs
    assert "miPriority.Click" in cs
    assert "StartPriorityExe()" in cs
    # Icon: vendor\\priority then ResolveTrayMenuIconPath (assets / bob\\tray\\assets).
    pri = cs.split("ToolStripMenuItem miPriority", 1)[1].split(
        "miAgents.DropDownItems.Add(miPriority)", 1
    )[0]
    assert 'Path.Combine(root, "vendor", "priority", "priority.ico")' in pri
    assert 'ResolveTrayMenuIconPath(root, "priority.ico")' in pri
    assert "9269" in pri


def test_fr9269_ps_priority_icon_assets_path():
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "vendor\\priority\\priority.ico" in ps
    assert "assets\\priority.ico" in ps
    assert "bob\\tray\\assets\\priority.ico" in ps
    assert "$miPriority.Add_Click({" in ps
    assert "Start-BobTrayPriorityExe" in ps


def test_fr9269_docs_pin_tray_assets():
    text = DOCS.read_text(encoding="utf-8")
    assert "9269" in text or "BOB-TRAY-UI-08" in text
    assert "tray/assets/priority.ico" in text.replace("\\", "/")
    assert "launcher/priority.ico" in text
