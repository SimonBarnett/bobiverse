"""FR #6819: /jeeves login form posts username, optional domain, password; never logs password."""
from __future__ import annotations

import json
import socket
import urllib.request

import jeeves_settings_http as http


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_fr6819_form_posts_three_fields_to_api_login():
    html = http._render_login_html()
    assert "/api/login" in html
    assert 'name="password"' in html
    assert 'name="account"' in html or 'name="username"' in html
    assert 'name="domain"' in html
    assert "domain:" in html
    assert "fd.get('domain')" in html or 'fd.get("domain")' in html


def test_fr6819_post_accepts_username_domain_password(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "h"
    home.mkdir()
    seen = []

    def auther(u, p, d=""):
        seen.append((u, d, p == "FAKE_login_ok"))
        return u == "simon" and d == "NTSA" and p == "FAKE_login_ok"

    port = _port()
    srv = http.start_settings_http(
        home, bind="127.0.0.1", port=port, authenticator=auther
    )
    assert srv is not None
    logs: list[str] = []
    orig = http._Handler.log_message

    def spy(self, fmt, *args):
        try:
            logs.append(fmt % args)
        except Exception:
            logs.append(str(fmt))
        return orig(self, fmt, *args)

    monkeypatch.setattr(http._Handler, "log_message", spy)
    try:
        body = json.dumps(
            {
                "username": "simon",
                "domain": "NTSA",
                "password": "FAKE_login_ok",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/login",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            doc = json.loads(resp.read().decode("utf-8"))
        assert doc.get("ok") is True
        assert seen == [("simon", "NTSA", True)]
        blob = "\n".join(logs)
        assert "FAKE_login_ok" not in blob
    finally:
        http.stop_settings_http(srv)
