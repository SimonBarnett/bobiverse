"""FR #7452: after login, /jeeves lands on home — not Settings."""
from __future__ import annotations

import json
import socket
import urllib.request
from http.cookiejar import CookieJar

import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.setenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    port = _free_port()
    srv = http.start_settings_http(
        chair,
        bind="127.0.0.1",
        port=port,
        digest_home=digest,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    assert srv is not None
    return srv, f"http://127.0.0.1:{port}"


def test_fr7452_login_html_redirects_to_home_not_settings():
    html = http._render_login_html(prefix="/jeeves")
    assert "location.href = '/jeeves/'" in html or 'location.href = "/jeeves/"' in html
    assert "/jeeves/settings" not in html.split("location.href")[1].split(";")[0]


def test_fr7452_home_html_has_cards_and_settings_nav():
    html = http._render_home_html(prefix="/jeeves")
    assert "Jeeves home" in html
    assert "Jeeves appliance settings" not in html
    for label in ("Queue", "Pools", "Status", "Commands", "Settings"):
        assert label in html
    assert "/jeeves/queue" in html
    assert "/jeeves/settings" in html
    assert "/jeeves/commands" in html
    assert 'aria-current="page"' in html


def test_fr7452_authenticated_root_is_home_settings_is_separate(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        login = urllib.request.Request(
            base + "/api/login",
            data=json.dumps(
                {"username": "ApplianceAdmin", "password": "FAKE_ok"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body.get("ok") is True

        with opener.open(base + "/", timeout=5) as resp:
            home = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "Jeeves home" in home
        assert "Jeeves appliance settings" not in home
        assert 'href="/settings"' in home

        with opener.open(base + "/settings", timeout=5) as resp:
            settings = resp.read().decode("utf-8")
        assert "Jeeves appliance settings" in settings
        assert "Jeeves home" not in settings
    finally:
        http.stop_settings_http(srv)


def test_fr7452_public_prefix_authenticated_jeeves_slash_is_home(tmp_path, monkeypatch):
    """Public mount: GET /jeeves/ after session is home; /jeeves/settings is settings.

    Public Set-Cookie uses Secure (HTTPS front door). Plain-HTTP urllib will not
    round-trip that cookie, so authenticate with Bearer like other /jeeves tests.
    """
    srv, base = _start(tmp_path, monkeypatch)
    try:
        login = urllib.request.Request(
            base + "/jeeves/api/login",
            data=json.dumps(
                {"username": "ApplianceAdmin", "password": "FAKE_ok"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(login, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body.get("ok") is True
        tok = str(body.get("session_token") or "")
        assert tok
        hdr = {"Authorization": f"Bearer {tok}"}

        req = urllib.request.Request(base + "/jeeves/", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            home = resp.read().decode("utf-8")
        assert "Jeeves home" in home
        assert "Jeeves appliance settings" not in home
        assert "/jeeves/settings" in home

        req = urllib.request.Request(
            base + "/jeeves/settings", headers=hdr, method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            settings = resp.read().decode("utf-8")
        assert "Jeeves appliance settings" in settings
    finally:
        http.stop_settings_http(srv)
