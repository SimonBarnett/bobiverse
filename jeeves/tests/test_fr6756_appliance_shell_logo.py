"""FR #6756: shared shell + NTSA logo bytes from git."""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import jeeves_settings_http as http

ROOT = Path(__file__).resolve().parents[2]
TRAY_LOGO = ROOT / "bob" / "tray" / "assets" / "ntsa-gut-logo.png"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
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


def _login(base: str) -> dict[str, str]:
    login = urllib.request.Request(
        base + "/api/login",
        data=json.dumps(
            {"username": "ApplianceAdmin", "password": "FAKE_ok"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login, timeout=5) as resp:
        tok = json.loads(resp.read().decode("utf-8"))["session_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_fr6756_logo_asset_matches_tray_bytes(tmp_path, monkeypatch):
    assert TRAY_LOGO.is_file()
    srv, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(base + "/assets/ntsa-gut-logo.png", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            ctype = resp.headers.get("Content-Type") or ""
            assert "png" in ctype.lower()
            body = resp.read()
        assert body == TRAY_LOGO.read_bytes()
    finally:
        http.stop_settings_http(srv)


def test_fr6756_four_pages_include_logo_path(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(base + "/login", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            login = resp.read().decode("utf-8")
        assert "/assets/ntsa-gut-logo.png" in login
        assert "User name" in login
        assert "Password" in login
        assert "Sign in" in login
        assert 'href="/logout"' not in login
        # FR #7274: one account field; Domain input removed.
        assert 'name="domain"' not in login
        assert 'name="account"' in login or 'name="username"' in login

        hdr = _login(base)
        pages = {}
        for path in ("/", "/status", "/queue"):
            req = urllib.request.Request(base + path, headers=hdr, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                pages[path] = resp.read().decode("utf-8")
            assert "/assets/ntsa-gut-logo.png" in pages[path]
            assert 'href="/"' in pages[path] or "Settings" in pages[path]
            assert 'href="/queue"' in pages[path]
            assert 'href="/status"' in pages[path]
            assert 'href="/logout"' in pages[path]
    finally:
        http.stop_settings_http(srv)


def test_fr6756_docs_name_shell():
    doc = (
        Path(__file__).resolve().parents[2]
        / "jeeves"
        / "docs"
        / "jeeves-settings-appliance.md"
    ).read_text(encoding="utf-8")
    assert "FR #6756" in doc
    assert "/assets/ntsa-gut-logo.png" in doc
