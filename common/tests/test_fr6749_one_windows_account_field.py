"""FR #6749 / FR-01: one Windows account field (DOMAIN\\user or user@domain)."""
from __future__ import annotations

import json

import jeeves_settings_auth as auth
import jeeves_settings_http as http


def test_fr6749_login_html_one_account_no_domain_input():
    html = http._render_login_html()
    assert 'name="account"' in html
    assert 'name="password"' in html
    assert 'name="domain"' not in html


def test_fr6749_logonuser_ntsa_slash_and_upn(monkeypatch):
    seen = []

    def fake_logon(user, domain, password):
        seen.append((user, domain))
        return False

    monkeypatch.setattr(auth, "_call_logon_user", fake_logon)
    auth.authenticate_windows_logon("NTSA\\simon", "FAKE_pw")
    auth.authenticate_windows_logon("simon@ntsa", "FAKE_pw")
    assert seen[0] == ("simon", "NTSA")
    assert seen[1] == ("simon", "ntsa")


def test_fr6749_failed_windows_logon_still_calls_credman(monkeypatch):
    cred_calls = []
    monkeypatch.setattr(auth, "_call_logon_user", lambda *a, **k: False)

    def cred(username, password):
        cred_calls.append(username)
        return False

    monkeypatch.setattr(auth, "authenticate_credman", cred)
    auth.default_authenticator("NTSA\\simon", "FAKE_pw")
    assert "NTSA\\simon" in cred_calls
    assert "simon" in cred_calls


def test_fr6749_login_json_still_accepts_domain_key(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    got = []

    def auther(u, p, d=""):
        got.append((u, d))
        return u == "simon" and d == "NTSA" and p == "FAKE_ok"

    r = auth.login(
        home,
        client_ip="10.0.0.8",
        username="simon",
        password="FAKE_ok",
        domain="NTSA",
        authenticator=auther,
    )
    assert r["ok"] is True
    assert got == [("simon", "NTSA")]
    assert "FAKE_ok" not in json.dumps(r)


def test_fr6749_error_never_includes_password(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    r = auth.login(
        home,
        client_ip="10.0.0.8",
        username="NTSA\\simon",
        password="super-secret-pw-xyz",
        authenticator=lambda *a, **k: False,
    )
    blob = json.dumps(r)
    assert r["ok"] is False
    assert "super-secret-pw-xyz" not in blob
