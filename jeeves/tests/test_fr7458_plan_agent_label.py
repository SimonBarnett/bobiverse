"""FR #7458: every Plan service link is labelled Plan Agent; old names gone.

Static check only: does not compute CSS or JavaScript visibility.
Hostnames are never hard-coded; the Plan destination is derived from the
home-page MCP anchor host (drop the first label for the site domain).
"""
from __future__ import annotations

import html as html_lib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobcallback  # noqa: E402
import jeeves_settings_http as http  # noqa: E402

WWW = ROOT / "jeeves" / "www" / "irc-ntsa"
HOME = WWW / "index.html"
PLAN_LABEL = "Plan Agent"
MCP_LABEL = "MCP"
# Assemble service labels so this module never embeds a full hostname.
_PLAN_LABEL_HOST = "plan"
_LEGACY_LABEL_HOST = "-".join(("skills", "visionary"))
_BANNED_VISIBLE = ("plan skills", "visionary")


class _PageCollector(HTMLParser):
    """Collect anchors and visible text (body, title, alt/aria-label/title)."""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._visible_parts: list[str] = []
        self._skip_depth = 0
        self._in_a = False
        self._a_href = ""
        self._a_aria = ""
        self._a_title = ""
        self._a_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        low = tag.lower()
        if low in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        for key in ("alt", "aria-label", "title"):
            if ad.get(key):
                self._visible_parts.append(ad[key])
        if low == "a":
            self._in_a = True
            self._a_href = ad.get("href", "")
            self._a_aria = ad.get("aria-label", "")
            self._a_title = ad.get("title", "")
            self._a_text = []

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if low == "a" and self._in_a:
            text = _norm_ws("".join(self._a_text))
            self.anchors.append(
                {
                    "href": self._a_href,
                    "text": text,
                    "aria-label": self._a_aria,
                    "title": self._a_title,
                }
            )
            self._in_a = False
            self._a_href = ""
            self._a_aria = ""
            self._a_title = ""
            self._a_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data:
            self._visible_parts.append(data)
            if self._in_a:
                self._a_text.append(data)

    def visible_text(self) -> str:
        return _norm_ws("".join(self._visible_parts))


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(s)).strip()


def _parse(html: str) -> _PageCollector:
    p = _PageCollector()
    p.feed(html)
    return p


def _domain_from_mcp(home_html: str) -> str:
    page = _parse(home_html)
    mcp = [a for a in page.anchors if a["text"] == MCP_LABEL]
    assert mcp, "home page must expose an MCP nav/link for domain derivation"
    host = urlparse(mcp[0]["href"]).hostname or ""
    parts = host.split(".")
    assert len(parts) >= 2, "MCP host must have a registrable domain"
    return ".".join(parts[1:])


def _is_plan_href(href: str, domain: str) -> bool:
    u = urlparse(href)
    host = (u.hostname or "").lower()
    return host in {
        f"{_PLAN_LABEL_HOST}.{domain}",
        f"{_LEGACY_LABEL_HOST}.{domain}",
    }


def _assert_plan_anchor(a: dict[str, str], domain: str) -> None:
    assert a["text"] == PLAN_LABEL, f"Plan link text must be {PLAN_LABEL!r}, got {a['text']!r}"
    for key in ("aria-label", "title"):
        val = a.get(key) or ""
        assert val in ("", PLAN_LABEL), f"Plan link {key} must be empty or {PLAN_LABEL!r}"
    u = urlparse(a["href"])
    assert u.scheme == "https"
    assert u.username is None and u.password is None
    assert u.port is None
    assert (u.path or "") in ("", "/")
    assert not u.query and not u.fragment
    host = (u.hostname or "").lower()
    assert host == f"{_PLAN_LABEL_HOST}.{domain}", (
        f"Plan link host must use {_PLAN_LABEL_HOST!r} label, got {host!r}"
    )


def _assert_no_banned_visible(html: str, where: str) -> None:
    page = _parse(html)
    low = page.visible_text().lower()
    for banned in _BANNED_VISIBLE:
        assert banned not in low, f"{where}: visible text must not contain {banned!r}"


def test_fr7458_static_pages_plan_agent_label():
    home = HOME.read_text(encoding="utf-8")
    domain = _domain_from_mcp(home)
    pages = sorted(WWW.rglob("*.html"))
    assert pages, "expected HTML under jeeves/www/irc-ntsa"

    plan_links: list[tuple[str, dict[str, str]]] = []
    for path in pages:
        html = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(WWW)).replace("\\", "/")
        _assert_no_banned_visible(html, rel)
        page = _parse(html)
        for a in page.anchors:
            if _is_plan_href(a["href"], domain):
                plan_links.append((rel, a))
                _assert_plan_anchor(a, domain)

    home_plans = [a for rel, a in plan_links if rel == "index.html"]
    assert home_plans, "home page must have at least one Plan Agent link"


def test_fr7458_jeeves_rendered_pages_ban_old_names(tmp_path: Path):
    home_html = HOME.read_text(encoding="utf-8")
    domain = _domain_from_mcp(home_html)

    chair = tmp_path / "chair"
    chair.mkdir()
    code, body = bobcallback.handle_request(
        "GET", "/jeeves", {}, b"", "8.8.8.8", chair, set()
    )
    assert code == 200
    pages = {
        "bobcallback:/jeeves": body.decode("utf-8"),
        "login": http._render_login_html(prefix="/jeeves"),
        "logout": http._render_login_html("Signed out.", prefix="/jeeves"),
        "settings": http._render_html(
            [
                {
                    "key": "sample_flag",
                    "group": "general",
                    "label": "Sample flag",
                    "type": "bool",
                    "value": False,
                }
            ],
            prefix="/jeeves",
        ),
        "queue": http._render_queue_html([], [], prefix="/jeeves"),
        "pools": http._render_pools_html(
            {
                "ok": True,
                "machines": [
                    {
                        "id": "box-a",
                        "remaining_pct": 50,
                        "fuel_stale": False,
                        "reset_label": "1 day",
                    }
                ],
            },
            prefix="/jeeves",
        ),
        "status": http._render_status_html(
            {
                "ok": True,
                "service": "ircJeeves",
                "uptime": "1h",
                "version": "0.0.0-test",
            },
            prefix="/jeeves",
        ),
    }
    for name, html in pages.items():
        _assert_no_banned_visible(html, name)
        page = _parse(html)
        for a in page.anchors:
            if _is_plan_href(a["href"], domain):
                _assert_plan_anchor(a, domain)
