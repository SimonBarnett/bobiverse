"""FR #7478: webhook docs pages carry the NTSA logo brand anchor (href=/)."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
WEBHOOKS = WWW / "docs" / "webhooks"
# Bookmark stubs: digest-local → report; models-validate retired → models.
STUB_REDIRECT_HTML = frozenset({"digest-local.html", "models-validate.html"})
LOGO_SRC = "/jeeves/assets/ntsa-gut-logo.png"
BRAND_RE = re.compile(
    r'<a\s+class=["\']brand["\']\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
LOGO_RE = re.compile(
    r'<img\b[^>]*\bsrc=["\']([^"\']*ntsa-gut-logo\.png)["\'][^>]*>',
    re.IGNORECASE,
)


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        ad = {k.lower(): (v or "") for k, v in attrs}
        if ad.get("href"):
            self.hrefs.append(ad["href"])


def _webhook_pages() -> list[Path]:
    pages = sorted(WEBHOOKS.glob("*.html"))
    assert len(pages) == 12, f"expected 12 webhook docs, got {len(pages)}"
    return pages


def _chrome_webhook_pages() -> list[Path]:
    return [p for p in _webhook_pages() if p.name not in STUB_REDIRECT_HTML]


def test_fr7478_webhook_docs_have_logo_brand_home_anchor():
    for path in _chrome_webhook_pages():
        html = path.read_text(encoding="utf-8")
        m = BRAND_RE.search(html)
        assert m, f"{path.name} missing a.brand href=/ logo anchor"
        assert m.group(1) == "/", f"{path.name} brand href must be / got {m.group(1)!r}"
        inner = m.group(2)
        logo = LOGO_RE.search(inner)
        assert logo, f"{path.name} brand missing ntsa-gut-logo.png img"
        assert logo.group(1) == LOGO_SRC or logo.group(1).endswith("ntsa-gut-logo.png")
        assert 'alt="' in inner.lower() or "alt='" in inner.lower()
        assert 'rel="icon"' in html.lower() or "rel='icon'" in html.lower()


def test_fr7478_detail_pages_keep_index_breadcrumb():
    for path in _chrome_webhook_pages():
        if path.name == "index.html":
            continue
        html = path.read_text(encoding="utf-8")
        p = _LinkCollector()
        p.feed(html)
        assert "index.html" in p.hrefs, f"{path.name} must link back to index.html"


def test_fr7478_stub_redirect_pages_refresh_to_canonical():
    """Stub HTML keep old URLs; they meta-refresh to the live docs page."""
    expect = {
        "digest-local.html": "report.html",
        "models-validate.html": "models.html",
    }
    for name, target in expect.items():
        path = WEBHOOKS / name
        assert path.is_file(), f"missing stub {name}"
        html = path.read_text(encoding="utf-8")
        assert f'url={target}' in html.lower() or f'url="{target}"' in html.lower()
        assert target in html
        assert 'rel="icon"' in html.lower() or "rel='icon'" in html.lower()
