"""FR #8728 / BOB-31: Workers > Open Code uses the opencode.ai favicon."""
import struct
from pathlib import Path

from repo_layout import REPO

ICO = REPO / "bob" / "tray" / "assets" / "opencode-favicon.ico"
PNG = REPO / "bob" / "tray" / "assets" / "opencode-favicon.png"
DOCS = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "opencode-favicon.png"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HTML = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "index.html"


def test_opencode_favicon_is_a_real_icon():
    raw = ICO.read_bytes()
    reserved, itype, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and itype == 1 and count >= 1
    assert PNG.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert DOCS.read_bytes() == PNG.read_bytes()


def test_tray_and_docs_use_opencode_favicon():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    html = HTML.read_text(encoding="utf-8")
    assert "opencode-favicon.ico" in cs
    assert "https://opencode.ai/favicon-v3.ico" in cs
    assert "assets\\opencode-favicon.ico" in ps
    assert "Workers Open Code: favicon" in ps
    assert 'src="opencode-favicon.png"' in html
    assert 'alt="opencode.ai favicon"' in html
