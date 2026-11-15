"""MRB #7568 hostile pins: front-door UI stays 404; /api/* is 401/403 not 404."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings_http as http


def _start(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.delenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", raising=False)
    home = tmp_path / "h"
    home.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    srv = http.start_settings_http(
        home, bind="127.0.0.1", port=port, authenticator=lambda u, p, d="": False
    )
    assert srv is not None
    return srv, f"http://127.0.0.1:{port}"


def test_mrb7568_lan_root_pages_stay_front_door_404(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    try:
        for path in ("/", "/login", "/status", "/queue", "/settings"):
            try:
                urllib.request.urlopen(base + path, timeout=5)
                raise AssertionError(f"expected front-door refuse for {path}")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, (path, exc.code)
                body = json.loads(exc.read().decode("utf-8"))
                assert body.get("ok") is False
                assert "jeeves" in str(body.get("error") or "").lower()
    finally:
        http.stop_settings_http(srv)


def test_mrb7568_unauth_put_api_settings_not_404(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(
            base + "/api/settings/agent.kind",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("put api key must require auth")
        except urllib.error.HTTPError as exc:
            assert exc.code in (401, 403), exc.code
            body = json.loads(exc.read().decode("utf-8"))
            assert body.get("ok") is False
    finally:
        http.stop_settings_http(srv)


def test_mrb7568_public_mount_login_still_200(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    try:
        with urllib.request.urlopen(base + "/jeeves/login", timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
        assert "login" in html.lower() or "sign in" in html.lower()
    finally:
        http.stop_settings_http(srv)
