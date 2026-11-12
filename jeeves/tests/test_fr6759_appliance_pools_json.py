"""FR #6759 / FR-11: GET /api/pools whitelist + LAN/session."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _fake_ghs() -> str:
    return "ghs_" + "FAKE_" + "POOL_MUST_DROP"


def _fake_email() -> str:
    return "seat" + "@" + "example.invalid"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _digest(home: Path, doc: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "digest.json").write_text(json.dumps(doc), encoding="utf-8")


def test_fr6759_zero_stays_zero_null_stays_null_no_copy(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _digest(
        digest,
        {
            "machines": {
                "flamingo": {
                    "remaining_pct": 0,
                    "fuel_stale": False,
                    "reset_label": "1h",
                    "token": _fake_ghs(),
                    "seat_email": _fake_email(),
                },
                "walrus": {
                    "remaining_pct": None,
                    "fuel_stale": True,
                    "reset_label": None,
                    "weekly": 99,
                },
            },
            "copilot": {
                "remaining": 12,
                "state": "ok",
                "reset_at": "2026-11-20T00:00:00Z",
                "fetched_at": "2026-11-12T12:00:00Z",
                "unlimited": False,
                "used": 8,
                "max_recorded_usage": 20,
                "plan": "drop-me",
                "source": "drop-me",
            },
            "overage_gbp": 1.5,
            "queue": {"secret": _fake_ghs()},
        },
    )
    view = js.api_get_pools(chair, digest_home=digest, client_ip="10.0.0.2")
    assert view["ok"] is True
    by_id = {row["id"]: row for row in view["machines"]}
    assert by_id["flamingo"]["remaining_pct"] == 0
    assert by_id["flamingo"]["remaining_pct"] is not None
    assert by_id["walrus"]["remaining_pct"] is None
    assert set(by_id["flamingo"].keys()) == {
        "id",
        "remaining_pct",
        "fuel_stale",
        "reset_label",
    }
    blob = json.dumps(view)
    assert "ghs_FAKE" not in blob
    assert "POOL_MUST_DROP" not in blob
    assert _fake_email() not in blob
    assert "seat_email" not in blob
    assert "token" not in blob
    assert "weekly" not in blob
    assert "plan" not in blob
    assert "queue" not in blob
    assert view["copilot"] == {
        "remaining": 12,
        "state": "ok",
        "reset_at": "2026-11-20T00:00:00Z",
        "fetched_at": "2026-11-12T12:00:00Z",
        "unlimited": False,
        "used": 8,
        "max_recorded_usage": 20,
    }
    assert view["overage_gbp"] == 1.5


def test_fr6759_omit_copilot_when_digest_has_none(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _digest(digest, {"machines": {"a": {"remaining_pct": 42}}})
    view = js.api_get_pools(chair, digest_home=digest, client_ip="127.0.0.1")
    assert view["ok"] is True
    assert "copilot" not in view
    assert view["overage_gbp"] is None
    assert view["machines"][0]["remaining_pct"] == 42


def test_fr6759_pools_non_lan_forbidden(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    view = js.api_get_pools(home, client_ip="8.8.8.8")
    assert view["ok"] is False
    assert "forbidden" in view["error"]


def test_fr6759_http_pools_session_required(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _digest(digest, {"machines": {}})
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
        unauth = urllib.request.Request(base + "/api/pools", method="GET")
        try:
            urllib.request.urlopen(unauth, timeout=5)
            raise AssertionError("expected 401 without session")
        except urllib.error.HTTPError as e:
            assert e.code == 401

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
        req = urllib.request.Request(base + "/api/pools", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body["ok"] is True
        assert body["machines"] == []
        assert "copilot" not in body
        assert body["overage_gbp"] is None
    finally:
        http.stop_settings_http(srv)


def test_fr6759_docs_name_pools_route():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "/api/pools" in doc
    assert "FR #6759" in doc
