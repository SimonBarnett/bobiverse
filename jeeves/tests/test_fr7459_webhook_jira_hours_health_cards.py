"""FR #7459: Webhooks & API section has Jira, Hours and Health cards."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "jeeves" / "www" / "irc-ntsa" / "index.html"

# Relative doc targets (no absolute hosts).
REQUIRED = (
    ("docs/webhooks/jira.html", "Jira"),
    ("docs/webhooks/hours.html", "Hours"),
    ("docs/webhooks/health-local.html", "Health"),
)


class _CardCollector(HTMLParser):
    """Collect article.card blocks: hrefs + heading/pill text inside each card."""

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, object]] = []
        self._in_card = False
        self._depth = 0
        self._hrefs: list[str] = []
        self._text_parts: list[str] = []
        self._capture_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        low = tag.lower()
        classes = ad.get("class", "").split()
        if low == "article" and "card" in classes:
            self._in_card = True
            self._depth = 1
            self._hrefs = []
            self._text_parts = []
            return
        if not self._in_card:
            return
        if low in ("article", "div", "section"):
            self._depth += 1
        if low == "a" and ad.get("href"):
            self._hrefs.append(ad["href"])
        if low in ("h3", "span") and "pill" in classes or low == "h3":
            self._capture_text = True

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if not self._in_card:
            return
        if low in ("h3", "span"):
            self._capture_text = False
        if low in ("article", "div", "section"):
            self._depth -= 1
            if low == "article" and self._depth <= 0:
                text = re.sub(r"\s+", " ", "".join(self._text_parts)).strip()
                self.cards.append({"hrefs": list(self._hrefs), "text": text})
                self._in_card = False
                self._depth = 0

    def handle_data(self, data: str) -> None:
        if self._in_card and self._capture_text and data:
            self._text_parts.append(data)


def _webhook_section(html: str) -> str:
    """Slice from Webhooks & API heading through the next section-title or footer."""
    m = re.search(
        r'<div class="section-title"[^>]*>\s*<h2>\s*Webhooks\s*&amp;\s*API\s*</h2>',
        html,
        re.I | re.S,
    )
    assert m, "home page must have a Webhooks & API section"
    start = m.start()
    rest = html[start:]
    nxt = re.search(
        r'<div class="section-title"|<footer\b',
        rest[m.end() - start :],
        re.I,
    )
    # m.end()-start is relative to rest; simpler: search after start+len
    after = html[m.end() :]
    end_m = re.search(r'<div class="section-title"|<footer\b', after, re.I)
    end = m.end() + (end_m.start() if end_m else len(after))
    return html[start:end]


def test_fr7459_webhooks_section_has_jira_hours_health_cards():
    html = HOME.read_text(encoding="utf-8")
    section = _webhook_section(html)
    assert 'class="card"' in section or "class='card'" in section

    parser = _CardCollector()
    parser.feed(section)
    assert parser.cards, "Webhooks & API section must contain cards"

    for href, label in REQUIRED:
        matches = [
            c
            for c in parser.cards
            if href in c["hrefs"] and label.lower() in str(c["text"]).lower()
        ]
        assert matches, (
            f"missing card for {label!r} linking to {href!r}; "
            f"cards={[(c['text'], c['hrefs']) for c in parser.cards]}"
        )
        # Same card style as Digest/Intake: pill + primary btn link.
        assert f'href="{href}"' in section or f"href='{href}'" in section
        assert "btn btn-primary" in section
        assert "pill" in section.lower()


def test_fr7459_required_doc_pages_exist():
    www = ROOT / "jeeves" / "www" / "irc-ntsa"
    for href, _label in REQUIRED:
        path = www / href.replace("/", "\\") if False else www.joinpath(*href.split("/"))
        assert path.is_file(), f"doc page missing: {href}"
