"""MRB #6829: public GET /jeeves is login; other appliance routes stay LAN-gated."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

import bobcallback
import jeeves_settings_http as http


def test_mrb6829_bobcallback_post_jeeves_is_not_login_html(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "POST", "/jeeves", {}, b"{}", "8.8.8.8", home, set()
    )
    assert code != 200 or b"password" not in body.lower()


def test_mrb6829_xff_status_still_403(tmp_path, monkeypatch):
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
            f"http://127.0.0.1:{port}/status",
            headers={"X-Forwarded-For": "8.8.8.8"},
            method="GET",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("GET /status with public XFF must not be 200")
        except urllib.error.HTTPError as e:
            assert e.code == 403
    finally:
        http.stop_settings_http(srv)
