"""Hostile pins for FR #6453 / MRB #6455 bob.ntsa.uk webhook docs."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import bobcallback
import bob_webhook_docs as docs


ROOT = Path(__file__).resolve().parents[2]
WWW = docs.www_root(ROOT)
GEN = ROOT / "common" / "scripts" / "gen_bob_webhook_docs_html.py"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"

_SECRETISH = re.compile(
    r"(?i)("
    r"gh[pousr]_[A-Za-z0-9_]{8,}"
    r"|github_pat_[A-Za-z0-9_]{8,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|Bearer\s+[A-Za-z0-9\-_\.=]{12,}"
    r"|password\s*=\s*\S+"
    r"|api[_-]?key\s*[:=]\s*\S+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r")"
)

_REQUIRED = (
    "purpose",
    "auth",
    "request_schema",
    "response_schema",
    "example_request",
    "status_codes",
    "retry_idempotency",
    "rate_limits",
    "reachability",
    "source",
    "fr",
)


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.hrefs.append(v)


def test_mrb6455_registry_required_fields_nonempty():
    for e in docs.all_entries():
        for k in _REQUIRED:
            assert getattr(e, k).strip(), f"{e.slug}.{k} empty"


def test_mrb6455_registry_examples_no_secretish():
    for e in docs.all_entries():
        m = _SECRETISH.search(e.example_request)
        assert m is None, f"{e.slug} example looks secretish: {m.group(0)[:40]}"


def test_mrb6455_every_post_route_has_inbound_doc():
    covered = {(e.method.upper(), e.path) for e in docs.inbound_entries()}
    for path in bobcallback.POST_ROUTES:
        assert ("POST", path) in covered, f"missing POST doc for {path}"


def test_mrb6455_front_page_links_each_inbound_html():
    index = WWW / "index.html"
    hrefs = _LinkCollector()
    hrefs.feed(index.read_text(encoding="utf-8"))
    joined = " ".join(hrefs.hrefs)
    for e in docs.inbound_entries():
        name = Path(e.html_rel).name
        assert name in joined, f"front page missing link to {name}"


def test_mrb6455_install_copies_docs_tree():
    text = INSTALL.read_text(encoding="utf-8")
    assert "www\\irc-ntsa" in text.replace("/", "\\") or "www/irc-ntsa" in text.replace("\\", "/")
    assert "docs" in text
    assert "Copy-Item" in text
    assert "-Recurse" in text
    assert "PhysicalPath" in text


def test_mrb6455_gen_and_registry_utf8_no_bom():
    for path in (GEN, ROOT / "common" / "scripts" / "bob_webhook_docs.py", WWW / "index.html"):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
        raw.decode("utf-8")
