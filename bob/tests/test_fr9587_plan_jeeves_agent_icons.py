# -*- coding: utf-8 -*-
"""FR #9587: TipForm Agents Plan (gantt) + Jeeves (butler) icons + loud MISSING.

Cursor unchanged. Plan/Jeeves re-vendor under bob/tray/assets; menu build logs
``menu-icon MISSING`` when the glyph is absent; apply at 16x16.
"""
from __future__ import annotations

import struct
from pathlib import Path

from repo_layout import REPO

ASSETS = REPO / "bob" / "tray" / "assets"
PLAN = ASSETS / "plan-gantt.ico"
BUTLER_TRAY = ASSETS / "jeeves-butler.ico"
BUTLER_JEEVES = REPO / "jeeves" / "assets" / "jeeves-butler.ico"
CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HELPER = REPO / "bob" / "tray" / "tools" / "BobTrayJeevesButler.ps1"


def _assert_real_ico(path: Path) -> None:
    raw = path.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1, path
    # Need a 16x16 (or 0=256) entry for ToolStripMenuItem paint.
    sizes = []
    for i in range(count):
        off = 6 + i * 16
        w = raw[off] or 256
        h = raw[off + 1] or 256
        sizes.append((w, h))
    assert (16, 16) in sizes, (path, sizes)


def test_fr9587_vendored_plan_and_jeeves_icos():
    for path in (PLAN, BUTLER_TRAY, BUTLER_JEEVES):
        assert path.is_file(), path
        _assert_real_ico(path)
    assert PLAN.read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert BUTLER_TRAY.read_bytes() == BUTLER_JEEVES.read_bytes()


def test_fr9587_tipform_jeeves_missing_log_and_16px():
    cs = CS.read_text(encoding="utf-8-sig")
    assert 'new Icon(butler, 16, 16)' in cs or "new Icon(butler, 16, 16)" in cs
    assert 'action", "menu-icon MISSING"' in cs
    assert "jeeves-butler.ico" in cs
    assert 'Path.Combine(rootPath, "bob", "tray", "assets", "jeeves-butler.ico")' in cs
    # Cursor path unchanged (Workers favicon).
    assert 'Path.Combine(installRoot ?? "", "assets", "menu-favicons", "cursor.com.ico")' in cs
    # Plan still via shared install-assets helper.
    assert 'TryApplyTrayMenuIcon(miPlan, root, "plan-gantt.ico", "plan")' in cs


def test_fr9587_watch_applies_plan_at_build_and_jeeves_missing():
    ps = WATCH.read_text(encoding="utf-8-sig")
    # Plan icon before Agents dropdown add (not deferred past MouseDown wiring).
    plan_idx = ps.find("$planGantt = Join-Path $RepoRoot 'assets\\plan-gantt.ico'")
    add_idx = ps.find("[void]$miAgents.DropDownItems.Add($miPlan)")
    assert plan_idx > 0 and add_idx > plan_idx
    assert "New-Object System.Drawing.Icon $planGantt, 16, 16" in ps
    assert "menu-icon MISSING file=plan-gantt.ico" in ps
    assert "menu-icon MISSING file=jeeves-butler.ico" in ps
    assert "New-Object System.Drawing.Icon $butler, 16, 16" in ps
    assert "bob\\tray\\tools\\BobTrayJeevesButler.ps1" in ps
    # Late deferred Plan block removed.
    assert ps.count("$planGantt = Join-Path $RepoRoot 'assets\\plan-gantt.ico'") == 1


def test_fr9587_butler_helper_tray_asset_fallback():
    helper = HELPER.read_text(encoding="utf-8-sig")
    assert "bob\\tray\\assets\\jeeves-butler.ico" in helper
    assert "jeeves\\assets\\jeeves-butler.ico" in helper
