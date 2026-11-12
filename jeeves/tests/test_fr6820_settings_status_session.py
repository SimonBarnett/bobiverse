"""FR #6820: settings and status stay behind the session cookie after public /jeeves."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

import jeeves_settings_http as http


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start(home, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    port = _port()
    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    return srv, f"http://127.0.0.1:{port}"


def test_fr6820_unauthenticated_settings_and_status_rejected(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    srv, base = _start(home, monkeypatch)
    assert srv is not None
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            settings_html = resp.read().decode("utf-8")
            assert resp.status == 200
        assert "password" in settings_html.lower()
        assert "Jeeves appliance settings" not in settings_html

        with urllib.request.urlopen(base + "/status", timeout=5) as resp:
            status_html = resp.read().decode("utf-8")
            assert resp.status == 200
        assert "password" in status_html.lower()
        assert "Token comparison by model" not in status_html
        assert "uptime_s" not in status_html

        req = urllib.request.Request(base + "/api/settings", method="GET")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("GET /api/settings without cookie must fail")
        except urllib.error.HTTPError as e:
            assert e.code in (401, 403)
    finally:
        http.stop_settings_http(srv)


def test_fr6820_session_cookie_opens_settings_and_status(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    srv, base = _start(home, monkeypatch)
    assert srv is not None
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
            doc = json.loads(resp.read().decode("utf-8"))
        assert doc.get("ok") is True
        assert http.SESSION_COOKIE_NAME in (resp.headers.get("Set-Cookie") or "")

        with opener.open(base + "/", timeout=5) as resp:
            settings_html = resp.read().decode("utf-8")
        assert "Jeeves appliance settings" in settings_html
        assert 'name="password"' not in settings_html

        with opener.open(base + "/status", timeout=5) as resp:
            status_html = resp.read().decode("utf-8")
        assert 'name="password"' not in status_html
        assert (
            "Token comparison" in status_html
            or "uptime" in status_html.lower()
            or "<svg" in status_html
            or "Nothing to compare" in status_html
        )
    finally:
        http.stop_settings_http(srv)
