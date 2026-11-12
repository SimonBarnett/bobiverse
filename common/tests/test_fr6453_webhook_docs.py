"""FR #6453: bob.ntsa.uk webhook/API docs pages stay in sync with registered routes."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import bobcallback
import bobhours
import bob_webhook_docs as docs


ROOT = Path(__file__).resolve().parents[2]
WWW = docs.www_root(ROOT)


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


def _collect_hrefs(html: str) -> list[str]:
    p = _LinkCollector()
    p.feed(html)
    return p.hrefs


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


def test_fr6453_registry_covers_bobcallback_post_and_public_get():
    """Every inbound BobCallback public route has a doc registry entry."""
    covered = {(e.method.upper(), e.path) for e in docs.inbound_entries()}
    for path in bobcallback.POST_ROUTES:
        assert ("POST", path) in covered, f"missing POST doc for {path}"
    assert ("GET", bobcallback.REPORT_PATH) in covered
    assert ("GET", bobcallback.JIRA_PATH) in covered
    assert ("GET", bobhours.HOURS_PATH) in covered
    # Hours action subpaths documented as patterns
    assert any(e.path.startswith(bobhours.HOURS_PATH + "/") for e in docs.inbound_entries())


def test_fr6453_every_registry_entry_has_html_page():
    missing = []
    for e in docs.all_entries():
        page = WWW / e.html_rel
        if not page.is_file():
            missing.append(str(e.html_rel))
            continue
        text = page.read_text(encoding="utf-8")
        assert e.title.split("(")[0].strip()[:12].lower() in text.lower() or e.slug in text
        assert e.method in text
        needle = e.path.split("{")[0]
        if "<" in needle:
            # Outbound wake URL is operator-configured; pin the env name instead.
            assert "JEEVES_TICKET_CLOSURE_WAKE_URL" in text
        else:
            assert needle in text
    assert not missing, f"missing HTML pages: {missing}"


def test_fr6453_docs_contain_no_secretish_strings():
    for path in WWW.rglob("*.html"):
        raw = path.read_text(encoding="utf-8")
        m = _SECRETISH.search(raw)
        assert m is None, f"secret-like string in {path.relative_to(WWW)}: {m.group(0)[:40]}"


def test_fr6453_front_page_keeps_acme_and_webhooks_section():
    index = (WWW / "index.html").read_text(encoding="utf-8")
    assert "bobiverse acme" in index.lower()
    assert "Webhooks &amp; API" in index or "Webhooks & API" in index
    hrefs = _collect_hrefs(index)
    webhook_links = [h for h in hrefs if "docs/webhooks" in h.replace("\\", "/")]
    assert webhook_links, "front page must link into docs/webhooks/"


def test_fr6453_front_page_links_resolve():
    index = WWW / "index.html"
    html = index.read_text(encoding="utf-8")
    hrefs = _collect_hrefs(html)
    # FR #6818: appliance login is a live site path, not a static file under www/.
    assert any(h.rstrip("/") == "/jeeves" for h in hrefs), "front page must link to /jeeves"
    for href in hrefs:
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Live site/API paths on the same host are not static files in www/.
        # /jeeves is the appliance UI (FR #6818); /bob/* are webhook routes.
        if href == "/" or href.startswith("/bob/") or href.rstrip("/") == "/jeeves":
            continue
        # Windows: Path(parent / "/abs") becomes drive-root absolute (e.g. D:\jeeves).
        if href.startswith("/"):
            continue
        target = (index.parent / href).resolve()
        assert target.is_file(), f"broken front-page link {href} -> {target}"


def test_fr6453_hub_links_to_each_inbound_page():
    hub = WWW / "docs" / "webhooks" / "index.html"
    assert hub.is_file()
    hrefs = set(_collect_hrefs(hub.read_text(encoding="utf-8")))
    for e in docs.inbound_entries():
        name = Path(e.html_rel).name
        assert any(name in h for h in hrefs), f"hub missing link to {name}"


def test_fr6453_install_bobwebhooks_copies_www():
    script = (
        ROOT / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
    ).read_text(encoding="utf-8")
    assert "irc-ntsa" in script
    assert "www" in script.lower() or "index.html" in script
    assert "Copy-Item" in script or "robocopy" in script.lower()


def test_fr6453_outbound_stall_wake_documented():
    entries = [e for e in docs.all_entries() if e.direction == "out"]
    assert entries, "expected outbound stall/wake doc entries"
    assert any("6391" in (e.fr or "") or "6439" in (e.fr or "") for e in entries)
