"""MRB #6836 hostile pins: butler ico served; public XFF GET not 403."""
from __future__ import annotations

import socket
import urllib.request
from pathlib import Path

import jeeves_settings_http as http

ICO = Path(__file__).resolve().parents[1] / "assets" / "jeeves-butler.ico"


def test_mrb6836_login_names_asset_path():
    html = http._render_login_html()
    assert "jeeves-butler.ico" in html
    assert "jeeves/assets/jeeves-butler.ico" in html
    assert 'alt="Jeeves the butler"' in html


def test_mrb6836_public_xff_get_butler_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "c"
    chair.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    srv = http.start_settings_http(chair, bind="127.0.0.1", port=port)
    assert srv is not None
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/assets/jeeves-butler.ico",
            headers={"X-Forwarded-For": "8.8.8.8"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read()
        assert body == ICO.read_bytes()
        assert body[:4] != b"\x89PNG"
    finally:
        http.stop_settings_http(srv)
