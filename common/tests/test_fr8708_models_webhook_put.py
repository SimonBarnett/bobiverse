"""BOB-02 / FR #8708: PUT /bob/v1/models persists Weights; GET round-trip."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request, make_handler, serve


REQUIRED = (
    "Plan",
    "Priority",
    "Jeeves",
    "Grok",
    "Cursor",
    "Opencode",
    "Opencode-Free",
    "Copilot",
)


def _full_agents(**overrides: dict) -> dict:
    rows = mc.default_agent_rows()
    for row in rows:
        if row["agent"] in overrides:
            row.update(overrides[row["agent"]])
    return {"agents": rows}


def test_put_then_get_round_trip(tmp_path: Path):
    body = json.dumps(
        _full_agents(Plan={"model": "build0.1", "context": "256", "effort": "med"})
    ).encode("utf-8")
    code, payload = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        body,
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 204
    assert payload == b""
    assert (tmp_path / mc.MODELS_CATALOG_NAME).is_file()

    code2, payload2 = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 200
    doc = json.loads(payload2.decode("utf-8"))
    plan = next(r for r in doc["agents"] if r["agent"] == "Plan")
    assert plan["model"] == "build0.1"
    assert plan["context"] == "256"
    assert plan["effort"] == "med"
    assert [r["agent"] for r in doc["agents"]] == list(REQUIRED)


def test_put_unchanged_returns_200(tmp_path: Path):
    body = json.dumps(_full_agents()).encode("utf-8")
    c1, _ = handle_request(
        "PUT", mc.MODELS_PATH, {}, body, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert c1 == 204
    c2, payload = handle_request(
        "PUT", mc.MODELS_PATH, {}, body, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert c2 == 200
    assert json.loads(payload.decode("utf-8"))["agents"]


def test_put_rejects_invalid_and_does_not_write(tmp_path: Path):
    before = list(tmp_path.iterdir())
    code, payload = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        b"not-json",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 400
    assert b"error" in payload
    assert list(tmp_path.iterdir()) == before

    code2, _ = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        json.dumps({"agents": [{"agent": "Unknown", "cli": "Grok"}]}).encode("utf-8"),
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 400
    assert not (tmp_path / mc.MODELS_CATALOG_NAME).exists()


def test_put_body_too_large_413(tmp_path: Path):
    huge = b'{"agents":"' + (b"x" * (mc.MODELS_PUT_MAX_BYTES + 10))
    code, _ = handle_request(
        "PUT", mc.MODELS_PATH, {}, huge, "127.0.0.1", tmp_path, allow_ips={"127.0.0.1"}
    )
    assert code == 413


def test_put_disallowed_peer_403(tmp_path: Path):
    body = json.dumps(_full_agents()).encode("utf-8")
    code, _ = handle_request(
        "PUT",
        mc.MODELS_PATH,
        {},
        body,
        "10.0.0.9",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 403
    assert not (tmp_path / mc.MODELS_CATALOG_NAME).exists()


def test_post_models_405(tmp_path: Path):
    code, _ = handle_request(
        "POST",
        mc.MODELS_PATH,
        {},
        b"{}",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 405


def test_loopback_listener_put_get_persists(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # serve() uses home from env / arg — follow hours/digest patterns via make_handler path.
    from bobcallback import DEFAULT_PORT
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = None
    ready = threading.Event()

    def _run():
        nonlocal server
        from http.server import ThreadingHTTPServer

        handler = make_handler(
            home=tmp_path,
            allow_ips={"127.0.0.1", "::1"},
            report_rate=None,
        )
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        ready.set()
        server.serve_forever(poll_interval=0.05)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert ready.wait(5)
    try:
        body = json.dumps(
            _full_agents(Grok={"model": "grok-live", "effort": "high"})
        ).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("PUT", "/bob/v1/models", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 204
        resp.read()
        conn.request("GET", "/bob/v1/models")
        resp2 = conn.getresponse()
        assert resp2.status == 200
        doc = json.loads(resp2.read().decode("utf-8"))
        grok = next(r for r in doc["agents"] if r["agent"] == "Grok")
        assert grok["model"] == "grok-live"
        conn.close()
        # Persist on disk after clear of in-memory — only file store.
        on_disk = json.loads((tmp_path / mc.MODELS_CATALOG_NAME).read_text(encoding="utf-8"))
        assert any(r.get("model") == "grok-live" for r in on_disk["agents"])
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        t.join(timeout=5)


def test_install_models_rule_forwards_put():
    from repo_layout import ROOT

    text = (ROOT / "jeeves" / "scripts" / "Install-BobWebhooks.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "BobModelsWebhook" in text
    assert "bob/v1/models" in text
    # FR #9273: public IIS rewrites PUT so Weights Save reaches bobcallback.
    assert 'pattern="^(GET|HEAD|POST|PUT)$"' in text
    assert "REQUEST_METHOD" in text
