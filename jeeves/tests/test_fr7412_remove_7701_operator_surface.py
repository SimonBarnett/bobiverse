"""FR #7412: sole settings UI is https://bob.ntsa.uk/jeeves; quiet :7701 removal."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings_http as http

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves" / "docs" / "jeeves-settings-appliance.md"
VISION = ROOT / "jeeves" / "VISION.md"


def test_fr7412_front_door_default_when_http_enabled(monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.delenv("JEEVES_SETTINGS_FRONTDOOR", raising=False)
    monkeypatch.delenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", raising=False)
    assert http.front_door_enabled() is True
    assert http.resolve_bind_host() == "127.0.0.1"


def test_fr7412_lan_root_escape_hatch(monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.setenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", "1")
    monkeypatch.delenv("JEEVES_SETTINGS_FRONTDOOR", raising=False)
    assert http.front_door_enabled() is False


def test_fr7412_direct_7701_root_does_not_serve_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    monkeypatch.delenv("JEEVES_SETTINGS_ALLOW_LAN_ROOT", raising=False)
    monkeypatch.setenv("JEEVES_SETTINGS_FRONTDOOR", "1")
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
        for path in ("/", "/login", "/status", "/queue"):
            try:
                urllib.request.urlopen(base + path, timeout=5)
                raise AssertionError(f"expected refuse for {path}")
            except urllib.error.HTTPError as e:
                assert e.code in (403, 404), (path, e.code)
        # Public mount still works (bobcallback proxies /jeeves*).
        with urllib.request.urlopen(base + "/jeeves/login", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        assert "Sign in" in body or "login" in body.lower()
        assert ":7701" not in body
    finally:
        http.stop_settings_http(srv)


def test_fr7412_docs_no_preferred_7701_howto():
    text = DOC.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/jeeves" in text
    assert "Do not browse `:7701`" in text or "not an operator URL" in text.lower()
    # Must not teach opening settings via :7701 as the how-to.
    assert "Browse `http://127.0.0.1:7701" not in text
    assert "Browse `http://jeeves.ntsa.uk:7701" not in text
    assert "### Deprecation" not in text and "## Deprecation" not in text
    assert "FR #7412" in text


def test_fr7412_vision_sole_public_jeeves():
    text = VISION.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/jeeves" in text
    assert "7412" in text
    # Quiet remove: may say "no deprecation brochure" but must not ship one.
    assert "deprecation brochure" in text.lower()
    assert "### Deprecation" not in text and "## Deprecation" not in text
