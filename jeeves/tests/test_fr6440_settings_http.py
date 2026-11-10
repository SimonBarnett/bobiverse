"""FR #6440: LAN-bound settings HTTP listener + schema UI (off by default)."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_fr6440_disabled_no_listener(monkeypatch):
    monkeypatch.delenv("JEEVES_SETTINGS_HTTP", raising=False)
    monkeypatch.delenv("JEEVES_SETTINGS_UI", raising=False)
    assert http.settings_http_enabled() is False
    srv = http.start_settings_http(Path("."), bind="127.0.0.1", port=_free_port())
    assert srv is None


def test_fr6440_refuse_non_lan_bind(monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    err = http.validate_bind_host("8.8.8.8")
    assert err is not None
    assert "LAN" in err or "RFC" in err or "forbidden" in err.lower()
    assert http.validate_bind_host("127.0.0.1") is None
    assert http.validate_bind_host("10.0.0.5") is None


def test_fr6440_non_lan_connect_refused(tmp_path, monkeypatch):
    """verify_request rejects non-RFC1918 client addresses at the socket layer."""
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "home"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(home, bind="127.0.0.1", port=port)
    assert srv is not None
    try:
        # Simulate a public peer: verify_request must return False.
        assert srv.verify_request(None, ("8.8.8.8", 12345)) is False
        assert srv.verify_request(None, ("10.1.2.3", 12345)) is True
        assert srv.verify_request(None, ("127.0.0.1", 9)) is True
    finally:
        http.stop_settings_http(srv)


def _login_bearer(base: str, *, username: str = "ApplianceAdmin", password: str = "FAKE_ok") -> str:
    req = urllib.request.Request(
        base + "/api/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body.get("ok") is True
    return str(body["session_token"])


def test_fr6440_get_put_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "home"
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
    try:
        tok = _login_bearer(base)
        hdr = {"Authorization": f"Bearer {tok}"}
        req = urllib.request.Request(base + "/api/settings", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body.get("ok") is True
        keys = {r["key"] for r in body.get("settings") or []}
        assert "BOB_CODERABBIT_WAIT_MIN" in keys
        # secrets never plaintext
        blob = json.dumps(body)
        assert "ghs_" not in blob

        req = urllib.request.Request(
            base + "/api/settings/BOB_CODERABBIT_WAIT_MIN",
            data=json.dumps({"value": "15", "actor": "tester"}).encode("utf-8"),
            headers={**hdr, "Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            put = json.loads(resp.read().decode("utf-8"))
        assert put.get("ok") is True
        assert put.get("backup_id")
        cfg = js.load_config_file(home)
        assert str(cfg.get("BOB_CODERABBIT_WAIT_MIN")) == "15"

        # HTML UI served after auth (cookie not set here; login page without bearer)
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
        assert "login" in html.lower() or "BOB_CODERABBIT_WAIT_MIN" in html
        assert "text/html" in (resp.headers.get("Content-Type") or "")
    finally:
        http.stop_settings_http(srv)


def test_fr6440_put_invalid_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "home"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(
        home,
        bind="127.0.0.1",
        port=port,
        authenticator=lambda u, p, d="": True,
    )
    assert srv is not None
    try:
        tok = _login_bearer(base := f"http://127.0.0.1:{port}", password="x")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/settings/BOB_CODERABBIT_WAIT_MIN",
            data=json.dumps({"value": "nope"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {tok}",
            },
            method="PUT",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as e:
            assert e.code in (400, 422)
            err = json.loads(e.read().decode("utf-8"))
            assert err.get("ok") is False
    finally:
        http.stop_settings_http(srv)


def test_fr6440_docs_enablement():
    root = Path(__file__).resolve().parents[2]
    doc = root / "jeeves" / "docs" / "jeeves-settings-appliance.md"
    text = doc.read_text(encoding="utf-8")
    assert "JEEVES_SETTINGS_HTTP" in text
    assert "7701" in text or "port" in text.lower()
    assert "FR #6440" in text
    assert "bob.ntsa.uk" in text


def test_fr6440_chair_jobs_wires_maybe_start():
    src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "chair_health.py"
    ).read_text(encoding="utf-8")
    assert "jeeves_settings_http" in src
    assert "maybe_start_from_chair" in src


def test_fr6440_build_manifest():
    build = (
        Path(__file__).resolve().parents[2]
        / "jeeves"
        / "scripts"
        / "Build-Jeeves.ps1"
    ).read_text(encoding="utf-8")
    assert "jeeves_settings" in build
    assert "jeeves_settings_http" in build
