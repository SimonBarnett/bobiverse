"""FR #6762 / FR-14: GET /pools overspend line only when GBP > 0."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_fr6762_format_overspend_line():
    assert http.format_overspend_line(1.5) == "overspend \u00a31.50"
    assert http.format_overspend_line(0) == ""
    assert http.format_overspend_line(None) == ""
    assert http.format_overspend_line("1.5") == "overspend \u00a31.50"
    html_pos = http._render_pools_html(1.5)
    assert html_pos.count("overspend") == 1
    assert "\u00a31.50" in html_pos
    html_zero = http._render_pools_html(0)
    assert "overspend" not in html_zero
    html_null = http._render_pools_html(None)
    assert "overspend" not in html_null


def _start(tmp_path, monkeypatch, digest_doc):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir(exist_ok=True)
    digest.mkdir(exist_ok=True)
    (digest / "digest.json").write_text(json.dumps(digest_doc), encoding="utf-8")
    port = _free_port()
    srv = http.start_settings_http(
        chair,
        bind="127.0.0.1",
        port=port,
        digest_home=digest,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    return srv, f"http://127.0.0.1:{port}"


def _login(base: str) -> str:
    login = urllib.request.Request(
        base + "/api/login",
        data=json.dumps(
            {"username": "ApplianceAdmin", "password": "FAKE_ok"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))["session_token"]


def _get_pools(base: str, tok: str) -> str:
    req = urllib.request.Request(
        base + "/pools",
        headers={"Authorization": f"Bearer {tok}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        return resp.read().decode("utf-8")


def test_fr6762_http_overspend_1_50(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch, {"overage_gbp": 1.5, "machines": {"a": {}}})
    try:
        tok = _login(base)
        body = _get_pools(base, tok)
        assert "overspend" in body
        assert "\u00a31.50" in body
        assert body.count("overspend") == 1
    finally:
        http.stop_settings_http(srv)


def test_fr6762_http_overspend_zero_and_null(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch, {"overage_gbp": 0})
    try:
        tok = _login(base)
        body = _get_pools(base, tok)
        assert "overspend" not in body
    finally:
        http.stop_settings_http(srv)
    srv, base = _start(tmp_path, monkeypatch, {"machines": {}})
    try:
        tok = _login(base)
        body = _get_pools(base, tok)
        assert "overspend" not in body
    finally:
        http.stop_settings_http(srv)


def test_fr6762_pools_unauth_login_html(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch, {"overage_gbp": 1.5})
    try:
        req = urllib.request.Request(base + "/pools", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
        assert "Sign in" in body or "login" in body.lower()
        assert "overspend" not in body.lower()
    finally:
        http.stop_settings_http(srv)


def test_fr6762_docs_name_overspend():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "GET /pools" in doc or "`/pools`" in doc
    assert "overspend" in doc.lower()
    assert "FR #6762" in doc
