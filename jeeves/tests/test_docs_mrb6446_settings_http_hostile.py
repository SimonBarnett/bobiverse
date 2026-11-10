"""docs/mrb-6446: hostile pins for FR #6440 LAN settings HTTP (PR #6446)."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_docs_mrb6446_maybe_start_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("JEEVES_SETTINGS_HTTP", raising=False)
    monkeypatch.delenv("JEEVES_SETTINGS_UI", raising=False)
    logs: list[str] = []
    assert http.maybe_start_from_chair(tmp_path, log=logs.append) is None
    assert logs == []


def test_docs_mrb6446_schema_and_rollback_http(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    home = tmp_path / "home"
    home.mkdir()
    port = _free_port()
    srv = http.start_settings_http(home, bind="127.0.0.1", port=port)
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(base + "/api/schema", timeout=5) as resp:
            schema = json.loads(resp.read().decode("utf-8"))
        assert schema.get("ok") is True
        keys = {r["key"] for r in schema.get("schema") or []}
        assert "BOB_CODERABBIT_WAIT_MIN" in keys

        put = urllib.request.Request(
            base + "/api/settings/BOB_CODERABBIT_WAIT_MIN",
            data=json.dumps({"value": "21", "actor": "hostile"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(put, timeout=5) as resp:
            put_body = json.loads(resp.read().decode("utf-8"))
        assert put_body.get("ok") is True
        backup_id = put_body.get("backup_id")
        assert backup_id

        rb = urllib.request.Request(
            base + "/api/rollback",
            data=json.dumps({"backup_id": backup_id, "actor": "hostile"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(rb, timeout=5) as resp:
            roll = json.loads(resp.read().decode("utf-8"))
        assert roll.get("ok") is True
        cfg = js.load_config_file(home)
        assert str(cfg.get("BOB_CODERABBIT_WAIT_MIN") or "") != "21" or "BOB_CODERABBIT_WAIT_MIN" not in cfg
    finally:
        http.stop_settings_http(srv)


def test_docs_mrb6446_build_keeps_settings_and_stall_imports():
    build = (
        Path(__file__).resolve().parents[2]
        / "jeeves"
        / "scripts"
        / "Build-Jeeves.ps1"
    ).read_text(encoding="utf-8")
    assert "jeeves_settings_http" in build
    assert "stall_callbacks" in build
    assert "<<<<<<<" not in build


def test_docs_mrb6446_vision_names_lan_http():
    vision = (
        Path(__file__).resolve().parents[2] / "jeeves" / "VISION.md"
    ).read_text(encoding="utf-8")
    assert "FR #6440" in vision
    assert "jeeves_settings_http" in vision
    assert "bob.ntsa.uk" in vision
