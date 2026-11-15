"""FR #7457: the MCP catalogue is always named Priority MCP."""
from __future__ import annotations

import re
from pathlib import Path

import jeeves_settings_http as http

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
CATALOGUE_HOST = "mcp.ntsa.uk"
LINK_RE = re.compile(
    r"<a\b([^>]*)>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
OLD_NAMES = (
    "MCP Catalogue",
    "MCP Catalog",
    "MCP catalogue",
    "MCP catalog",
    "Priority skills",
    "Priority skill catalog",
    "Priority skill catalogue",
    "Open MCP catalog",
)


def _visible(inner: str) -> str:
    text = re.sub(r"<[^>]+>", " ", inner)
    return re.sub(r"\s+", " ", text).strip()


def _pages() -> list[tuple[str, str]]:
    rows = [(str(p.relative_to(WWW)), p.read_text(encoding="utf-8")) for p in WWW.rglob("*.html")]
    pre = "/jeeves"
    rows.append(("appliance-home", http._render_home_html(prefix=pre)))
    rows.append(("appliance-login", http._render_login_html(prefix=pre)))
    return rows


def test_fr7457_catalogue_links_say_priority_mcp_only():
    seen = 0
    for name, html in _pages():
        low = html.lower()
        for old in OLD_NAMES:
            assert old.lower() not in low, f"{name} still says {old!r}"
        for attrs, inner in LINK_RE.findall(html):
            href_m = HREF_RE.search(attrs)
            if not href_m or CATALOGUE_HOST not in href_m.group(1).lower():
                continue
            seen += 1
            assert _visible(inner) == "Priority MCP", (
                f"{name} link text {_visible(inner)!r} for {href_m.group(1)}"
            )
    assert seen >= 4, "expected catalogue links on the public site"
