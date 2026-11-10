"""FR #6451: LAN settings HTTP requires FR #6441 sessions (cookie/bearer)."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

import jeeves_settings_auth as auth
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _opener_with_cookies() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def test_fr6451_unauthenticated_api_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "h"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": True,
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        for path, method, data in (
            ("/api/settings", "GET", None),
            (
                "/api/settings/BOB_CODERABBIT_WAIT_MIN",
                "PUT",
                json.dumps({"value": "9"}).encode("utf-8"),
            ),
            (
                "/api/rollback",
                "POST",
                json.dumps({"backup_id": "nope"}).encode("utf-8"),
            ),
        ):
            req = urllib.request.Request(base + path, data=data, method=method)
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                urllib.request.urlopen(req, timeout=5)
                assert False, f"expected HTTPError for {method} {path}"
            except urllib.error.HTTPError as e:
                assert e.code in (401, 403), (path, e.code)
                body = json.loads(e.read().decode("utf-8"))
                assert body.get("ok") is False
                assert "unauthorized" in str(body.get("error") or "").lower()
    finally:
        http.stop_settings_http(srv)


def test_fr6451_login_cookie_then_get_put(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    home = tmp_path / "h"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    opener, jar = _opener_with_cookies()
    try:
        login_req = urllib.request.Request(
            base + "/api/login",
            data=json.dumps(
                {"username": "ApplianceAdmin", "password": "FAKE_ok"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login_req, timeout=5) as resp:
            login = json.loads(resp.read().decode("utf-8"))
            set_cookie = resp.headers.get("Set-Cookie") or ""
        assert login.get("ok") is True
        assert login.get("session_token")
        assert "FAKE_ok" not in json.dumps(login)
        assert http.SESSION_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie

        with opener.open(base + "/api/settings", timeout=5) as resp:
            view = json.loads(resp.read().decode("utf-8"))
        assert view.get("ok") is True

        put_req = urllib.request.Request(
            base + "/api/settings/BOB_CODERABBIT_WAIT_MIN",
            data=json.dumps({"value": "17"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with opener.open(put_req, timeout=5) as resp:
            put = json.loads(resp.read().decode("utf-8"))
        assert put.get("ok") is True

        # Bearer also works (no cookie).
        tok = login["session_token"]
        br = urllib.request.Request(
            base + "/api/settings",
            headers={"Authorization": f"Bearer {tok}"},
            method="GET",
        )
        with urllib.request.urlopen(br, timeout=5) as resp:
            assert json.loads(resp.read().decode("utf-8")).get("ok") is True

        # Password never lands in session store.
        raw = (home / auth.SESSION_STORE).read_text(encoding="utf-8")
        assert "FAKE_ok" not in raw
    finally:
        http.stop_settings_http(srv)


def test_fr6451_login_page_and_html_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "h"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": True,
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert resp.status == 200
        assert "login" in html.lower()
        assert "password" in html.lower()
        assert "FAKE_" not in html
    finally:
        http.stop_settings_http(srv)


def test_fr6451_docs_mention_http_auth_wire():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "6451" in doc or "session" in doc.lower()
    assert "cookie" in doc.lower() or "Bearer" in doc or "login" in doc.lower()
