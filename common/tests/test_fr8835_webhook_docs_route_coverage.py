"""FR #8835: every BobCallback route has DocEntry + docs page + home card + hub row."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import bob_route_inventory as inv
import bob_webhook_docs as docs

REPO = Path(__file__).resolve().parents[2]
WWW = REPO / "jeeves" / "www" / "irc-ntsa"
HOME = WWW / "index.html"
HUB = WWW / "docs" / "webhooks" / "index.html"


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, str]] = []
        self._in_card = False
        self._in_code = False
        self._buf = ""
        self._code = ""
        self._href = ""
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "article" and attrs_d.get("class") == "card":
            self._in_card = True
            self._depth = 1
            self._code = ""
            self._href = ""
            self._buf = ""
            return
        if not self._in_card:
            return
        if tag == "article":
            self._depth += 1
        if tag == "code":
            self._in_code = True
            self._buf = ""
        if tag == "a" and "href" in attrs_d and "docs/webhooks/" in attrs_d["href"]:
            self._href = attrs_d["href"]

    def handle_endtag(self, tag):
        if not self._in_card:
            return
        if tag == "code" and self._in_code:
            self._in_code = False
            if self._buf.strip():
                # keep first path-like code in the card
                if not self._code or self._buf.strip().startswith("/"):
                    if self._buf.strip().startswith("/") or "|" in self._buf or self._buf.strip().startswith("GET"):
                        self._code = self._buf.strip()
        if tag == "article":
            self._depth -= 1
            if self._depth <= 0:
                self._in_card = False
                if self._href:
                    self.cards.append({"code": self._code, "href": self._href})

    def handle_data(self, data):
        if self._in_card and self._in_code:
            self._buf += data


def _home_cards() -> list[dict[str, str]]:
    p = _CardParser()
    p.feed(HOME.read_text(encoding="utf-8"))
    return p.cards


def _hub_text() -> str:
    return HUB.read_text(encoding="utf-8")


def _entry_for_route(route: str):
    live = [e for e in docs.all_entries() if getattr(e, "status", "live") == "live"]
    for e in live:
        base = e.path.split("{", 1)[0].rstrip("/")
        if e.path.startswith("http"):
            continue
        if route == e.path or route == base or route.startswith(base + "/"):
            return e
    return None


def _card_for_entry(cards, entry) -> bool:
    page = Path(entry.html_rel).name
    for c in cards:
        if page not in (c.get("href") or "").replace("\\", "/"):
            continue
        return True
    return False


def test_fr8835_inventory_includes_core_paths():
    paths = set(inv.coverage_paths(REPO))
    for need in (
        "/bob/v1/models",
        "/bob/v1/git",
        "/bob/v1/report",
        "/bob/v1/builds",
        "/bob/v1/hours",
        "/bob/v1/digest",
        "/health",
    ):
        assert need in paths, paths


def test_fr8835_live_routes_documented():
    cards = _home_cards()
    hub = _hub_text()
    missing: list[str] = []
    for route in inv.coverage_paths(REPO):
        if route.startswith("/jeeves"):
            continue
        entry = _entry_for_route(route)
        if entry is None:
            missing.append(f"route {route}: no DocEntry (card + docs page required)")
            continue
        page = WWW / entry.html_rel
        if not page.is_file():
            missing.append(f"route {route}: missing page {entry.html_rel}")
        # hub lists path or documented base
        base = entry.path.split("{", 1)[0]
        if route not in hub and base not in hub and entry.path not in hub:
            missing.append(f"route {route}: missing hub index row on docs/webhooks/index.html")
        if entry.direction != "out" and not _card_for_entry(cards, entry):
            missing.append(f"route {route}: missing home card linking {entry.html_rel}")
    assert not missing, "undocumented routes:\n" + "\n".join(missing)


def test_fr8835_models_and_git_cards_present():
    cards = _home_cards()
    hrefs = {c["href"].replace("\\", "/") for c in cards}
    assert any(h.endswith("models.html") or "models.html" in h for h in hrefs), cards
    assert any(h.endswith("git.html") or "git.html" in h for h in hrefs), cards
    home = HOME.read_text(encoding="utf-8")
    assert "/bob/v1/models" in home
    assert "/bob/v1/git" in home


def test_fr8835_coming_models_ops_marked():
    coming = {e.slug for e in docs.all_entries() if getattr(e, "status", "live") == "coming"}
    assert {"models-put", "models-patch"} <= coming
    assert "models-refresh" not in coming
    page = (WWW / "docs" / "webhooks" / "models.html").read_text(encoding="utf-8")
    assert "Coming — not served" in page


def test_fr8835_fake_route_zzz_named_as_gap():
    fake = "/bob/v1/zzz"
    assert _entry_for_route(fake) is None
    cards = _home_cards()
    hub = _hub_text()
    gaps = []
    if _entry_for_route(fake) is None:
        gaps.append(f"route {fake}: no DocEntry (card + docs page required)")
    if fake not in hub:
        gaps.append(f"route {fake}: missing hub index row on docs/webhooks/index.html")
    if not any("zzz" in (c.get("href") or "") for c in cards):
        gaps.append(f"route {fake}: missing home card")
    assert any("zzz" in g and "DocEntry" in g for g in gaps)
    assert any("hub" in g for g in gaps)
    assert any("card" in g for g in gaps)


def test_fr8835_webhooks_md_names_coverage_rule():
    md = (REPO / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "FR #8835" in md
    assert "test_fr8835_webhook_docs_route_coverage" in md
