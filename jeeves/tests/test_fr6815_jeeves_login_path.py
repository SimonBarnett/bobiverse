"""FR #6815: GET /jeeves returns appliance login HTML; not 403; /bob/v1/* unchanged."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import bobcallback
import jeeves_settings_http as http


def test_fr6815_bobcallback_get_jeeves_is_login_not_403(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    code, body = bobcallback.handle_request(
        "GET", "/jeeves", {}, b"", "8.8.8.8", home, set()
    )
    assert code != 403
    assert code == 200
    html = body.decode("utf-8")
    assert 'type="password"' in html or "type='password'" in html
    assert "password" in html.lower()


def test_fr6815_bob_v1_report_still_matches(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "registered-machines.json").write_text(
        json.dumps({"machines": ["flamingo"]}), encoding="utf-8"
    )
    code, body = bobcallback.handle_request(
        "GET", "/bob/v1/report", {}, b"", "127.0.0.1", home, {"127.0.0.1"}
    )
    assert code == 200
    doc = json.loads(body.decode("utf-8"))
    assert isinstance(doc, dict)


def test_fr6815_appliance_xff_public_jeeves_not_403(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "c"
    chair.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    srv = http.start_settings_http(chair, bind="127.0.0.1", port=port)
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(
            base + "/jeeves",
            headers={"X-Forwarded-For": "8.8.8.8"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status != 403
            assert resp.status == 200
            html = resp.read().decode("utf-8")
        assert "password" in html.lower()
    except urllib.error.HTTPError as e:
        raise AssertionError(f"GET /jeeves was HTTP {e.code}") from e
    finally:
        http.stop_settings_http(srv)
