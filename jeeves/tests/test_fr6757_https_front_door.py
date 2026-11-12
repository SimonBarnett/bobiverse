"""FR #6757: HTTPS front door, loopback-only bind, X-Forwarded-For LAN gate."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def test_fr6757_xff_loopback_public_rejected():
    ip = js.effective_client_ip("127.0.0.1", "8.8.8.8")
    assert js.reject_non_lan(ip)


def test_fr6757_xff_loopback_rfc1918_accepted():
    ip = js.effective_client_ip("127.0.0.1", "10.0.0.8")
    assert js.reject_non_lan(ip) is None


def test_fr6757_non_loopback_public_ignores_xff():
    ip = js.effective_client_ip("8.8.8.8", "10.0.0.8")
    assert js.reject_non_lan(ip)


def test_fr6757_front_door_forces_loopback_bind(monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_FRONTDOOR", "1")
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP_BIND", "10.0.0.5")
    assert http.resolve_bind_host() == "127.0.0.1"


def test_fr6757_login_html_has_no_port_7701():
    html = http._render_login_html()
    assert ":7701" not in html


def test_fr6757_http_xff_from_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "c"
    chair.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    srv = http.start_settings_http(
        chair,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": False,
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        bad = urllib.request.Request(
            base + "/login",
            headers={"X-Forwarded-For": "8.8.8.8"},
            method="GET",
        )
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("expected 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403

        ok = urllib.request.Request(
            base + "/login",
            headers={"X-Forwarded-For": "10.1.1.9"},
            method="GET",
        )
        with urllib.request.urlopen(ok, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        assert "Sign in" in body or "login" in body.lower()
        assert ":7701" not in body
    finally:
        http.stop_settings_http(srv)


def test_fr6757_docs_https_no_browse_7701():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "https://jeeves.ntsa.uk/" in doc
    assert "Browse `http://jeeves.ntsa.uk:7701/" not in doc
    assert "FR #6757" in doc
    assert "win-acme" not in doc.lower()
    script = (
        root / "jeeves" / "scripts" / "Install-JeevesApplianceFrontDoor.ps1"
    ).read_text(encoding="utf-8")
    assert "127.0.0.1:7701" in script
    assert "jeeves.ntsa.uk" in script
    assert "Thumbprint" in script or "thumbprint" in script
    assert "win-acme" not in script.lower()
    assert "cloudflare.com" not in script.lower()
    assert "Let's Encrypt" not in script
    assert "No Cloudflare" in script or "does not bind bob.ntsa.uk" in script
