"""FR #8723 / BOB-19: Workers > Grok uses the grok.com favicon."""
import struct
from pathlib import Path

from repo_layout import REPO

ICO = REPO / "bob" / "tray" / "assets" / "grok-favicon.ico"
PNG = REPO / "bob" / "tray" / "assets" / "grok-favicon.png"
DOCS = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "grok-favicon.png"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HTML = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "index.html"


def test_grok_favicon_is_a_real_icon():
    raw = ICO.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1
    assert PNG.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert DOCS.read_bytes() == PNG.read_bytes()


def test_tray_and_docs_use_grok_favicon_not_a_generic_icon():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    html = HTML.read_text(encoding="utf-8")
    assert "grok-favicon.ico" in cs
    assert "https://grok.com/images/favicon.ico" in cs
    assert "SystemIcons" not in cs
    assert "assets\\grok-favicon.ico" in ps
    assert "Workers Grok: favicon" in ps
    assert 'src="grok-favicon.png"' in html
    assert 'alt="grok.com favicon"' in html
