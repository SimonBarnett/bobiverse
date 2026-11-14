"""FR #7274: /jeeves prefix-aware URLs, no Domain field, Bob link, cookie Path=/jeeves."""
from __future__ import annotations

from pathlib import Path

import bobcallback
import jeeves_settings_http as http


def test_fr7274_split_ui_path_public_vs_lan():
    assert http.split_ui_path("/jeeves") == ("/jeeves", "/login")
    assert http.split_ui_path("/jeeves/") == ("/jeeves", "/")
    assert http.split_ui_path("/jeeves/api/login") == ("/jeeves", "/api/login")
    assert http.split_ui_path("/jeeves/assets/ntsa-gut-logo.png") == (
        "/jeeves",
        "/assets/ntsa-gut-logo.png",
    )
    assert http.split_ui_path("/") == ("", "/")
    assert http.split_ui_path("/api/login") == ("", "/api/login")


def test_fr7274_ui_href_prefix():
    assert http.ui_href("", "/api/login") == "/api/login"
    assert http.ui_href("/jeeves", "/api/login") == "/jeeves/api/login"
    assert http.ui_href("/jeeves", "/") == "/jeeves/"
    assert http.ui_href("/jeeves", "/assets/x.png") == "/jeeves/assets/x.png"


def test_fr7274_login_html_public_prefix_no_domain_bob_link():
    html = http._render_login_html(prefix="/jeeves")
    assert "/jeeves/api/login" in html
    assert "/jeeves/assets/ntsa-gut-logo.png" in html
    assert "/jeeves/assets/jeeves-butler.ico" in html
    assert "name=\"domain\"" not in html
    assert "Domain (optional)" not in html
    assert "bob.ntsa.uk" in html
    assert "/bob/v1/report" in html
    assert "location.href = '/jeeves/'" in html or 'location.href = "/jeeves/"' in html
    assert "LAN-only" not in html


def test_fr7274_login_html_lan_keeps_root_urls():
    html = http._render_login_html()
    assert "fetch('/api/login'" in html or 'fetch("/api/login"' in html
    assert "/assets/ntsa-gut-logo.png" in html
    assert "name=\"domain\"" not in html


def test_fr7274_parse_account_user_domain():
    assert http.parse_account(r"NTSA\simon", "") == ("simon", "NTSA")
    assert http.parse_account("simon@ntsa.uk", "") == ("simon", "ntsa.uk")
    assert http.parse_account("simon", "NTSA") == ("simon", "NTSA")
    assert http.parse_account("simon", "") == ("simon", "")


def test_fr7274_cookie_path_jeeves_secure():
    hdr = http.session_cookie_header("tok", max_age=60, prefix="/jeeves", secure=True)
    assert "Path=/jeeves" in hdr
    assert "HttpOnly" in hdr
    assert "SameSite=Strict" in hdr
    assert "Secure" in hdr
    lan = http.session_cookie_header("tok", max_age=60, prefix="", secure=False)
    assert "Path=/" in lan
    assert "Secure" not in lan


def test_fr7274_bobcallback_jeeves_login_uses_prefix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET", "/jeeves", {}, b"", "8.8.8.8", home, set()
    )
    assert code == 200
    html = body.decode("utf-8")
    assert "/jeeves/api/login" in html
    assert "/jeeves/assets/ntsa-gut-logo.png" in html
    assert "name=\"domain\"" not in html
    assert "bob.ntsa.uk" in html


def test_fr7274_bobcallback_serves_jeeves_assets(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET",
        "/jeeves/assets/ntsa-gut-logo.png",
        {},
        b"",
        "8.8.8.8",
        home,
        set(),
    )
    assert code == 200
    assert body[:8] == b"\x89PNG\r\n\x1a\n" or len(body) > 40
    code2, body2 = bobcallback.handle_request(
        "GET",
        "/jeeves/assets/jeeves-butler.ico",
        {},
        b"",
        "8.8.8.8",
        home,
        set(),
    )
    assert code2 == 200
    assert len(body2) > 10


def test_fr7274_public_route_table_covers_prefix():
    routes = http.public_jeeves_routes()
    assert "/jeeves" in routes
    assert "/jeeves/" in routes
    assert "/jeeves/api/login" in routes
    assert "/jeeves/assets/ntsa-gut-logo.png" in routes
    assert "/jeeves/logout" in routes
