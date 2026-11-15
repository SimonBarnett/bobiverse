"""FR #7409: bob.ntsa.uk home redesign — shared chrome, nav, webhook discoverability."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WWW = ROOT / "jeeves" / "www" / "irc-ntsa"
HOME = WWW / "index.html"
SITE_CSS = WWW / "site.css"


def test_fr7409_home_has_primary_nav_hrefs():
    text = HOME.read_text(encoding="utf-8")
    assert 'href="/downloads"' in text
    assert 'href="/jeeves"' in text
    assert "https://mcp.ntsa.uk" in text
    assert "https://github.com/SimonBarnett/bobiverse" in text
    assert ">Home<" in text
    assert ">Downloads<" in text
    assert ">Jeeves<" in text
    assert ">MCP<" in text or ">GitHub<" in text
    assert ">GitHub<" in text


def test_fr7409_home_links_shared_site_css_tokens():
    html = HOME.read_text(encoding="utf-8")
    assert re.search(r'href=["\'](?:\./)?site\.css["\']', html), "home must link site.css"
    css = SITE_CSS.read_text(encoding="utf-8")
    for token in ("--ink", "--gold", "--charcoal", "--paper"):
        assert token in css, f"missing token {token}"


def test_fr7409_webhook_docs_still_discoverable():
    text = HOME.read_text(encoding="utf-8")
    assert "docs/webhooks/index.html" in text or "/docs/webhooks" in text
    assert "webhook" in text.lower()


def test_fr7409_site_css_has_narrow_viewport_nav_guard():
    css = SITE_CSS.read_text(encoding="utf-8")
    assert "400px" in css or "max-width: 400" in css.replace(" ", "")
    assert "overflow-x" in css
