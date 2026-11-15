"""FR #7528: /downloads vertical list; airc always last; one-column #download-grid."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
CSS = WWW / "site.css"
INDEX = WWW / "downloads" / "index.html"
EMPTY = WWW / "downloads" / "empty.html"
ERROR = WWW / "downloads" / "error.html"
MOCK = REPO / "jeeves" / "docs" / "mocks" / "bob-ntsa-public-front-door" / "downloads.html"
MOCK_CSS = REPO / "jeeves" / "docs" / "mocks" / "bob-ntsa-public-front-door" / "site.css"
REQUIRED_BEFORE_AIRC = ("bob", "jeeves", "priority-agent")


class DownloadGridCards(HTMLParser):
    """Collect direct article.card data-product values under #download-grid."""

    def __init__(self) -> None:
        super().__init__()
        self.in_grid = False
        self.grid_depth = 0
        self.products: list[str] = []
        self._pending_product: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "div" and ad.get("id") == "download-grid":
            self.in_grid = True
            self.grid_depth = 1
            return
        if self.in_grid:
            if tag in ("div", "section", "main", "article"):
                self.grid_depth += 1
            # Direct child articles only: depth == 2 (grid=1, article=2 just entered)
            if tag == "article" and self.grid_depth == 2 and "card" in ad.get("class", "").split():
                prod = ad.get("data-product", "")
                if prod:
                    self.products.append(prod)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_grid:
            return
        if tag in ("div", "section", "main", "article"):
            self.grid_depth -= 1
            if self.grid_depth <= 0:
                self.in_grid = False
                self.grid_depth = 0


def card_products(html: str) -> list[str]:
    p = DownloadGridCards()
    p.feed(html)
    return p.products


def assert_airc_last(products: list[str], *, label: str) -> None:
    assert products.count("airc") == 1, (label, products)
    assert products[-1] == "airc", (label, products)
    for name in REQUIRED_BEFORE_AIRC:
        assert name in products[:-1], (label, name, products)


def test_fr7528_index_empty_error_mock_airc_last():
    for path in (INDEX, EMPTY, ERROR, MOCK):
        html = path.read_text(encoding="utf-8")
        assert 'id="download-grid"' in html, path.name
        assert "insert new cards above this line" in html, path.name
        products = card_products(html)
        assert_airc_last(products, label=path.name)


def test_fr7528_extra_card_after_airc_rejected():
    html = INDEX.read_text(encoding="utf-8")
    # Inject a synthetic card after airc inside the grid.
    poisoned = html.replace(
        "</article>\n    </div>\n\n    <p style=\"margin-top:1.25rem",
        '</article>\n      <article class="card" data-product="extra">x</article>\n'
        '    </div>\n\n    <p style="margin-top:1.25rem',
        1,
    )
    if poisoned == html:
        # Fallback: append before closing grid via airc marker end
        poisoned = re.sub(
            r'(data-product="airc">.*?</article>)(\s*</div>)',
            r'\1\n      <article class="card" data-product="extra">x</article>\2',
            html,
            count=1,
            flags=re.S,
        )
    products = card_products(poisoned)
    assert products[-1] == "extra"
    try:
        assert_airc_last(products, label="poisoned")
    except AssertionError:
        return
    raise AssertionError("expected airc-last helper to reject extra trailing card")


def test_fr7528_css_one_column_download_grid_keeps_shared_three():
    css = CSS.read_text(encoding="utf-8")
    assert re.search(
        r"#download-grid\s*\{[^}]*grid-template-columns:\s*1fr",
        css,
        re.S,
    ), "missing #download-grid one-column rule"
    assert "order:" not in css.split("#download-grid")[1].split("}")[0]
    # Shared .grid still three columns on wide viewports
    assert re.search(
        r"\.grid\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*1fr\)",
        css,
        re.S,
    )
    mock_css = MOCK_CSS.read_text(encoding="utf-8")
    assert "#download-grid" in mock_css
    assert "grid-template-columns: 1fr" in mock_css


def test_fr7528_index_cards_keep_controls():
    html = INDEX.read_text(encoding="utf-8")
    for product in ("bob", "jeeves", "priority-agent"):
        m = re.search(
            rf'<article\s+class="card"\s+data-product="{product}">(.*?)</article>',
            html,
            re.S,
        )
        assert m, product
        card = m.group(1)
        assert "Release notes" in card or 'data-role="release-notes"' in card, product
        if product != "priority-agent":
            assert 'data-role="msi"' in card
            # FR #7530: sha256 href filled at runtime; static pin is data-role.
            assert 'data-role="sha256"' in card or ".sha256" in card
        else:
            assert 'data-role="assets"' in card
            assert 'data-role="release-notes"' in card
            assert "priority-mcp/releases" in card
    airc = re.search(
        r'<article\s+class="card"\s+data-product="airc">(.*?)</article>',
        html,
        re.S,
    )
    assert airc
    assert 'data-role="install-snippet"' in airc.group(1)
    assert 'data-role="copy-install"' in airc.group(1)
