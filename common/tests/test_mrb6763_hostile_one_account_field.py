"""MRB #6763 hostile pins for FR #6749 one Windows account field."""
from __future__ import annotations

import json
import socket
import urllib.request

import jeeves_settings_auth as auth
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_mrb6763_json_domain_used_when_username_has_no_split(monkeypatch):
    seen = []

    def fake_logon(user, domain, password):
        seen.append((user, domain, password))
        return False

    monkeypatch.setattr(auth, "_call_logon_user", fake_logon)
    pw = "FAKE_" + "logon"
    auth.authenticate_windows_logon("simon", pw, domain="NTSA")
    assert seen == [("simon", "NTSA", pw)]


def test_mrb6763_slash_and_upn_override_json_domain(monkeypatch):
    seen = []
    monkeypatch.setattr(
        auth,
        "_call_logon_user",
        lambda u, d, p: seen.append((u, d)) or False,
    )
    pw = "FAKE_" + "pw"
    auth.authenticate_windows_logon("OTHER\\simon", pw, domain="NTSA")
    auth.authenticate_windows_logon("simon@corp.example", pw, domain="NTSA")
    assert seen[0] == ("simon", "OTHER")
    assert seen[1] == ("simon", "corp.example")


def test_mrb6763_windows_success_skips_credman(monkeypatch):
    cred_calls = []
    monkeypatch.setattr(auth, "_call_logon_user", lambda *a, **k: True)
    monkeypatch.setattr(
        auth,
        "authenticate_credman",
        lambda u, p: cred_calls.append(u) or True,
    )
    assert auth.default_authenticator("NTSA\\simon", "FAKE_" + "ok") is True
    assert cred_calls == []


def test_mrb6763_login_html_js_omits_domain_key():
    html = http._render_login_html()
    assert "fd.get('account')" in html
    assert "domain:" not in html
    assert 'name="domain"' not in html


def test_mrb6763_http_login_accepts_account_and_legacy_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "h"
    home.mkdir()
    port = _free_port()
    got = []

    def auther(u, p, d=""):
        got.append((u, p, d))
        return u == "simon" and d == "NTSA" and p == ("FAKE_" + "ok")

    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=auther,
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        body = json.dumps(
            {
                "account": "simon",
                "password": "FAKE_" + "ok",
                "domain": "NTSA",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            base + "/api/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        assert doc.get("ok") is True
        assert got == [("simon", "FAKE_" + "ok", "NTSA")]
        assert ("FAKE_" + "ok") not in json.dumps(doc)
    finally:
        http.stop_settings_http(srv)


def test_mrb6763_error_password_uses_fake_placeholder(tmp_path):
    """GG-safe password fixture (parts); must never appear in login error JSON."""
    home = tmp_path / "h"
    home.mkdir()
    secret = "FAKE_" + "pw_" + "mrb6763"
    r = auth.login(
        home,
        client_ip="10.0.0.8",
        username="NTSA\\simon",
        password=secret,
        authenticator=lambda *a, **k: False,
    )
    blob = json.dumps(r)
    assert r["ok"] is False
    assert secret not in blob
