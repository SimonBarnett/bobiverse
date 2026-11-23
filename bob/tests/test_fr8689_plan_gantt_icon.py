"""FR #8689 / BOB-48: Plan menu uses the skills-visionary GANTT asset."""
import struct
from pathlib import Path

from repo_layout import REPO

ICO = REPO / "bob" / "tray" / "assets" / "plan-gantt.ico"
PNG = REPO / "bob" / "tray" / "assets" / "plan-gantt.png"
DOCS_PNG = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "plan-gantt.png"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HTML = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "index.html"


def test_plan_gantt_asset_is_the_visionary_icon():
    assert ICO.is_file()
    raw = ICO.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1
    assert PNG.is_file() and PNG.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert DOCS_PNG.read_bytes() == PNG.read_bytes()


def test_tray_and_docs_name_the_gantt_path_not_a_generic_icon():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    html = HTML.read_text(encoding="utf-8")
    # FR #9267: ResolveTrayMenuIconPath prefers install assets\ then bob\tray\assets\.
    assert "plan-gantt.ico" in cs
    assert "ResolveTrayMenuIconPath" in cs
    assert 'TryApplyTrayMenuIcon(miPlan, root, "plan-gantt.ico"' in cs
    assert 'Path.Combine(rootPath, "assets", name)' in cs
    assert 'Path.Combine(rootPath, "bob", "tray", "assets", name)' in cs
    idx = cs.find("plan-gantt.ico")
    assert "SystemIcons" not in cs[max(0, idx - 400) : idx + 500]
    assert "assets\\plan-gantt.ico" in ps
    assert "bob\\tray\\assets\\plan-gantt.ico" in ps
    assert "Plan: GANTT icon" in ps
    assert 'src="plan-gantt.png"' in html
    assert 'alt="Plan GANTT"' in html
