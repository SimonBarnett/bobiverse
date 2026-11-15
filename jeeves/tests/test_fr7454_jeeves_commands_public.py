"""FR #7454: /jeeves/commands is public (no login); other /jeeves pages stay gated."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "tests"))

import bobcallback  # noqa: E402
import jeeves_settings_http as http  # noqa: E402


CORE_VERBS = ("!help", "!list", "!focus", "!assign")


def test_fr7454_commands_html_has_list_and_site_chrome():
    raw = http.load_jeeves_commands_html()
    assert raw is not None
    text = raw.decode("utf-8")
    for verb in CORE_VERBS:
        assert verb in text
    assert "site.css" in text
    assert 'class="site-header"' in text
    assert "/jeeves/commands" in text
    assert "password" not in text.lower()


def test_fr7454_login_and_nav_link_to_commands():
    login = http._render_login_html(prefix="/jeeves")
    assert "/jeeves/commands" in login
    assert "password" in login.lower()
    home = http._render_home_html(prefix="/jeeves")
    assert "/jeeves/commands" in home
    assert "/jeeves/commands" in http.public_jeeves_routes()


def test_fr7454_bobcallback_unauth_commands_is_200(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET", "/jeeves/commands", {}, b"", "8.8.8.8", home, set()
    )
    assert code == 200
    text = body.decode("utf-8")
    for verb in CORE_VERBS:
        assert verb in text
    assert "password" not in text.lower()
    # Must not be the settings login page.
    assert "Jeeves settings login" not in text


def test_fr7454_bobcallback_jeeves_root_stays_login(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET", "/jeeves", {}, b"", "8.8.8.8", home, set()
    )
    assert code == 200
    text = body.decode("utf-8")
    assert "password" in text.lower() or "Sign in" in text
    assert "!help" not in text


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_settings(tmp_path, monkeypatch):
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


def test_fr7454_settings_http_commands_public_queue_gated(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request

    srv, base = _start_settings(tmp_path, monkeypatch)
    try:
        with urllib.request.urlopen(base + "/jeeves/commands", timeout=5) as resp:
            assert resp.status == 200
            text = resp.read().decode("utf-8")
        for verb in CORE_VERBS:
            assert verb in text
        assert "password" not in text.lower()

        # Other appliance pages still require login (login HTML, not commands).
        with urllib.request.urlopen(base + "/jeeves/queue", timeout=5) as resp:
            assert resp.status == 200
            q = resp.read().decode("utf-8")
        assert "Sign in" in q or "password" in q.lower()
        assert "!help" not in q
    finally:
        http.stop_settings_http(srv)


def test_fr7454_bobcallback_does_not_proxy_commands(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("commands must not proxy to settings upstream")

    monkeypatch.setattr(bobcallback, "_proxy_jeeves_settings", boom)
    code, body = bobcallback.handle_request(
        "GET", "/jeeves/commands/", {}, b"", "8.8.8.8", home, set()
    )
    assert called["n"] == 0
    assert code == 200
    assert b"!help" in body
