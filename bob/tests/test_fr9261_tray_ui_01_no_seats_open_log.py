# -*- coding: utf-8 -*-
"""FR #9261 / BOB-TRAY-UI-01: no top-level Seats: or Open log; About Show logs remains."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIALOGS = ROOT / "tray" / "dialogs"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr9261_bobtray_cs_no_top_seats_or_open_log():
    src = (DIALOGS / "BobTray.cs").read_text(encoding="utf-8-sig")
    assert 'new ToolStripMenuItem("Seats: on")' not in src
    assert 'MenuItems.Add("Seats: on")' not in src
    assert 'Item("Open log"' not in src
    assert "FR #9261" in src
    about = (DIALOGS / "BobAbout.cs").read_text(encoding="utf-8-sig")
    assert 'logs.Text = "Show logs"' in about
    assert "watch_bob_tray.log" in about


def test_fr9261_watch_ps_no_top_open_log():
    text = WATCH.read_text(encoding="utf-8")
    assert "$menu.Items.Add('Open log')" not in text
    assert "$miLog" not in text
    assert "FR #9261" in text
    assert "Show logs" in text


def test_fr9487_docs_menu_inventory_no_open_log():
    """FR #9487: bob-tray-dialogs.md menu inventory matches TipForm after #9261."""
    docs = (ROOT / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    assert "FR #9261" in docs or "BOB-TRAY-UI-01" in docs
    assert "Show logs" in docs
    # Menu bullet must not advertise a top-level Open log item.
    menu_line = next(
        (ln for ln in docs.splitlines() if ln.lstrip().startswith("* **Menu**")),
        "",
    )
    assert menu_line, "expected Menu inventory bullet"
    # Inventory lists Status…Exit only; must not name Open log as a menu entry.
    assert "**Open log**" not in menu_line
    assert "Show logs" in menu_line
    assert "FR #9261" in menu_line or "#9487" in menu_line
    # Stale prose must not claim a top-level Open log action remains.
    assert "**Open log** opens" not in docs
