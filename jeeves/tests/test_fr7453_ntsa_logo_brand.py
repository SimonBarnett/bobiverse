"""FR #7453: NTSA logo replaces letter brand mark; brand always links to `/`."""
from __future__ import annotations

import re
from pathlib import Path

import jeeves_settings_http as http

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
# Meta-refresh stubs (digest→report; no models/validate) keep bookmarks; no site chrome.
STUB_REDIRECT_HTML = frozenset({"digest-local.html", "models-validate.html"})
LOGO_SRC_RE = re.compile(
    r'src=["\']([^"\']*ntsa-gut-logo\.png)["\']', re.IGNORECASE
)
BRAND_ANCHOR_RE = re.compile(
    r'<a\s+class=["\']brand["\']\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
LETTER_MARK_RE = re.compile(
    r'class=["\']brand-mark["\'][^>]*>\s*[A-Za-z]\s*<', re.IGNORECASE
)


def _served_html_files() -> list[Path]:
    """Every served static HTML under irc-ntsa (FR #7453 / #7478; no site-header filter)."""
    return sorted(
        p for p in WWW.rglob("*.html") if p.name not in STUB_REDIRECT_HTML
    )


def test_fr7453_site_chrome_pages_use_logo_inside_home_anchor():
    files = _served_html_files()
    assert files, "expected HTML under irc-ntsa"
    for path in files:
        html = path.read_text(encoding="utf-8")
        assert not LETTER_MARK_RE.search(html), f"{path.name} still has letter brand-mark"
        m = BRAND_ANCHOR_RE.search(html)
        assert m, f"{path.name} missing class=brand anchor"
        assert m.group(1) == "/", f"{path.name} brand href must be / got {m.group(1)!r}"
        inner = m.group(2)
        logo = LOGO_SRC_RE.search(inner)
        assert logo, f"{path.name} brand anchor missing ntsa-gut-logo.png img"
        assert "ntsa-gut-logo.png" in logo.group(1)


def test_fr7453_appliance_shell_logo_links_home_not_letter():
    for prefix in ("", "/jeeves"):
        hdr = http._shell_header(current="home", include_nav=True, prefix=prefix)
        assert not LETTER_MARK_RE.search(hdr)
        m = BRAND_ANCHOR_RE.search(hdr)
        assert m, f"prefix={prefix!r} missing brand"
        assert m.group(1) == "/"
        assert "ntsa-gut-logo.png" in m.group(2)
        assert "brand-logo" in m.group(2) or "<img" in m.group(2).lower()


def test_fr7453_every_appliance_page_document_has_logo_home_brand():
    pre = "/jeeves"
    pages = {
        "login": http._render_login_html(prefix=pre),
        "home": http._render_home_html(prefix=pre),
        "settings": http._render_html([], prefix=pre),
        "queue": http._render_queue_html([], [], prefix=pre),
        "pools": http._render_pools_html({"machines": []}, prefix=pre),
        "status": http._render_status_html(
            {
                "version": "0",
                "source_commit": "",
                "uptime_s": 0,
                "queue": {"unaccepted": 0, "accepted": 0},
                "seats": {"live_n": 0, "idle_n": 0},
                "fuel": {"active": []},
                "restart_pending": False,
            },
            prefix=pre,
        ),
    }
    for name, html in pages.items():
        assert not LETTER_MARK_RE.search(html), f"{name} letter mark"
        m = BRAND_ANCHOR_RE.search(html)
        assert m, f"{name} missing brand"
        assert m.group(1) == "/", f"{name} brand href"
        assert "ntsa-gut-logo.png" in m.group(2), f"{name} missing logo img"
