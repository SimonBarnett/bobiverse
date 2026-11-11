"""FR #6443: restart-when-idle + read-only appliance status (no secrets)."""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import gitclaim
import jeeves_settings as js
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _queue(home: Path, *, accepted=None, unaccepted=None):
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": list(unaccepted or []),
        "accepted": list(accepted or []),
        "done": [],
    }
    (home / "queue.json").write_text(json.dumps(doc), encoding="utf-8")


def test_fr6443_restart_deferred_while_accepted(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(
        digest,
        accepted=[
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#1",
                "accepted_by": "redqueen-1",
            }
        ],
    )
    calls: list[str] = []

    def boom():
        calls.append("restart")
        return {"ok": True, "via": "test"}

    out = js.request_restart_when_idle(
        chair,
        digest_home=digest,
        client_ip="10.0.0.8",
        actor="tester",
        restart_fn=boom,
    )
    assert out["ok"] is True
    assert out.get("deferred") is True
    assert "accepted" in str(out.get("reason") or "").lower() or out.get("pending")
    assert calls == []
    assert js.restart_pending_path(chair).is_file()

    # Tick while still busy: still deferred.
    tick = js.tick_restart_when_idle(
        chair, digest_home=digest, restart_fn=boom
    )
    assert tick.get("deferred") is True or tick.get("skipped")
    assert calls == []


def test_fr6443_restart_runs_when_idle(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(digest, accepted=[])
    calls: list[str] = []

    def boom():
        calls.append("restart")
        return {"ok": True, "via": "test"}

    out = js.request_restart_when_idle(
        chair,
        digest_home=digest,
        client_ip="127.0.0.1",
        actor="tester",
        restart_fn=boom,
    )
    assert out["ok"] is True
    assert out.get("restarted") is True
    assert calls == ["restart"]
    assert not js.restart_pending_path(chair).is_file()


def test_fr6443_pending_fires_after_accepted_clears(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(
        digest,
        accepted=[{"task": "MRB", "repo": "a/b", "id": "#9", "accepted_by": "x"}],
    )
    calls: list = []
    js.request_restart_when_idle(
        chair,
        digest_home=digest,
        client_ip="10.1.1.1",
        actor="ui",
        restart_fn=lambda: calls.append(1) or {"ok": True},
    )
    assert calls == []
    _queue(digest, accepted=[])
    tick = js.tick_restart_when_idle(
        chair,
        digest_home=digest,
        restart_fn=lambda: calls.append(1) or {"ok": True},
    )
    assert tick.get("restarted") is True
    assert calls == [1]


def test_fr6443_status_fields_no_secrets(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(
        digest,
        unaccepted=[{"task": "FR", "repo": "a/b", "id": "#2"}],
        accepted=[],
    )
    monkeypatch.setenv("GH_TOKEN", "ghs_FAKE_STATUS_MUST_NOT_LEAK")
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    view = js.api_get_status(
        chair,
        digest_home=digest,
        client_ip="10.0.0.2",
        started=1000.0,
        now=1060.0,
        version="9.9.9",
        source_commit="abc123deadbeef",
    )
    assert view["ok"] is True
    assert view["version"] == "9.9.9"
    assert view["source_commit"] == "abc123deadbeef"
    assert view["uptime_s"] == 60
    assert view["queue"]["unaccepted"] == 1
    assert view["queue"]["accepted"] == 0
    assert "seats" in view
    assert "fuel" in view
    assert view["fuel"].get("coderabbit") is True
    blob = json.dumps(view)
    assert "ghs_FAKE" not in blob
    assert "MUST_NOT_LEAK" not in blob
    assert "password" not in blob.lower() or "password" not in str(view)


def test_fr6443_status_non_lan_forbidden(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    view = js.api_get_status(home, client_ip="8.8.8.8")
    assert view["ok"] is False
    assert "forbidden" in view["error"]


def test_fr6443_restart_never_names_ergo():
    src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "jeeves_settings.py"
    ).read_text(encoding="utf-8")
    # Product restart helper must only target ircJeeves.
    assert "ircJeeves" in src
    assert "BobIrcd" not in src or "never" in src.lower()
    assert "restart_ircjeeves" in src or "RESTART_SERVICE" in src


def test_fr6443_http_status_and_restart_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(digest, accepted=[])
    port = _free_port()
    calls: list = []
    monkeypatch.setattr(
        js,
        "restart_ircjeeves_only",
        lambda: calls.append("r") or {"ok": True, "via": "test"},
    )
    # FR #6451 / #6509: status + restart endpoints require session (cookie/Bearer).
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

        req = urllib.request.Request(
            base + "/api/status", headers=hdr, method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body.get("ok") is True
        assert "uptime_s" in body
        assert "queue" in body

        req = urllib.request.Request(base + "/status", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8")
        assert "uptime" in html.lower() or "queue" in html.lower()

        req = urllib.request.Request(
            base + "/api/restart-when-idle",
            data=json.dumps({"actor": "ui"}).encode("utf-8"),
            headers={**hdr, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        assert out.get("ok") is True
        assert calls == ["r"] or out.get("restarted") or out.get("deferred") is not None
    finally:
        http.stop_settings_http(srv)


def test_fr6443_docs_and_wiring():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "FR #6443" in doc
    assert "restart" in doc.lower()
    assert "/api/status" in doc or "status" in doc.lower()
    ch = (root / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    assert "tick_restart_when_idle" in ch
