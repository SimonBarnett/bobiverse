"""FR #6761 / FR-13: Copilot pool line on GET /pools (tray sentence, once)."""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _digest(home: Path, doc: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "digest.json").write_text(json.dumps(doc), encoding="utf-8")


def test_fr6761_format_remaining_37():
    line = http.format_copilot_pool_line({"remaining": 37, "state": "ok"})
    assert line.startswith("Copilot - 37% left")
    assert "unknown" not in line


def test_fr6761_format_missing_unknown():
    assert http.format_copilot_pool_line(None) == "Copilot - unknown"
    assert http.format_copilot_pool_line({}) == "Copilot - unknown"


def test_fr6761_format_stale_keeps_percent_and_marker():
    line = http.format_copilot_pool_line(
        {"remaining": 12, "state": "ok", "fuel_stale": True}
    )
    assert "Copilot - 12% left" in line
    assert "[stale]" in line


def test_fr6761_pools_html_copilot_once_under_machines():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {"id": "walrus", "remaining_pct": 42, "fuel_stale": False},
                {"id": "flamingo", "remaining_pct": 10, "fuel_stale": False},
            ],
            "copilot": {"remaining": 37, "state": "ok"},
            "overage_gbp": None,
        }
    )
    assert html.count("Copilot - 37% left") == 1
    assert "Copilot - 37% left" in html
    # Under machine rows: machine list appears before the Copilot line.
    assert html.index("walrus") < html.index("Copilot - 37% left")
    assert html.index("flamingo") < html.index("Copilot - 37% left")


def test_fr6761_pools_html_unknown_when_no_copilot():
    html = http._render_pools_html(
        {"ok": True, "machines": [], "overage_gbp": None}
    )
    assert "Copilot - unknown" in html
    assert html.count("Copilot -") == 1


def test_fr6761_http_pools_page_session(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _digest(
        digest,
        {
            "machines": {
                "a": {"remaining_pct": 1, "fuel_stale": False},
                "b": {"remaining_pct": 2, "fuel_stale": False},
            },
            "copilot": {"remaining": 37, "state": "ok"},
        },
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
    base = f"http://127.0.0.1:{port}"
    try:
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
        hdr = {"Authorization": f"Bearer {tok}"}
        req = urllib.request.Request(base + "/pools", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        assert body.count("Copilot - 37% left") == 1
        assert body.index("a") < body.index("Copilot - 37% left")
        assert body.index("b") < body.index("Copilot - 37% left")
    finally:
        http.stop_settings_http(srv)


def test_fr6761_docs_mention_copilot_line():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "FR #6761" in doc or "FR-13" in doc
    assert "Copilot" in doc
