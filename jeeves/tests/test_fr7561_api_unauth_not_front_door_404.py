"""FR #7561: front-door LAN root still hides the UI, but /api/* is 401 not 404."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings_http as http


def test_fr7561_unauth_api_is_401_root_stays_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.delenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", raising=False)
    home = tmp_path / "h"
    home.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    srv = http.start_settings_http(home, bind="127.0.0.1", port=port, authenticator=lambda u, p, d="": False)
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        try:
            urllib.request.urlopen(base + "/", timeout=5)
            raise AssertionError("root must stay hidden")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        req = urllib.request.Request(base + "/api/settings", method="GET")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("api must require auth")
        except urllib.error.HTTPError as exc:
            assert exc.code in (401, 403)
            body = json.loads(exc.read().decode("utf-8"))
            assert body.get("ok") is False
            assert "unauthorized" in str(body.get("error") or "").lower()
    finally:
        http.stop_settings_http(srv)
