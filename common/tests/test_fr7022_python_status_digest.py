"""FR #7022: python-status.json feeds digest peer fuel merge (missing / source tag only)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat
import pytest


MID = "flamingo"


def _peer(**extra):
    base = {
        "ok": True,
        "id": MID,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "pcent": {"grok-chat": 42},
        "lastSeen": "2026-11-13T11:00:00Z",
    }
    base.update(extra)
    return base


def _write_python_status(home: Path, *, python: str = "missing", ok: bool = False) -> Path:
    run = home / "run"
    run.mkdir(parents=True, exist_ok=True)
    path = run / "python-status.json"
    path.write_text(
        json.dumps({"ok": ok, "python": python, "detail": "test", "at": 1}) + "\n",
        encoding="utf-8",
    )
    return path


def _fake_urlopen(posted: list):
    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    return fake_urlopen


def test_fr7022_python_in_merge_fields():
    assert "python" in bobreport._MERGE_PEER_FIELDS
    assert "python" in bobreport._TRAY_MACHINE_EXPORT_KEYS


def test_fr7022_builder_includes_python_missing():
    body = bobreport.build_peer_fuel_merge_payload(_peer(python="missing"), MID)
    assert body is not None
    assert body.get("python") == "missing"


def test_fr7022_builder_includes_source_tag():
    body = bobreport.build_peer_fuel_merge_payload(
        _peer(python="env:BOBIVERSE_PYTHON"), MID
    )
    assert body is not None
    assert body.get("python") == "env:BOBIVERSE_PYTHON"


def test_fr7022_sanitize_rejects_path_body():
    assert bobreport.sanitize_python_digest_tag("missing") == "missing"
    assert bobreport.sanitize_python_digest_tag("stamp:config") == "stamp:config"
    assert bobreport.sanitize_python_digest_tag(r"C:\Python\Python312\python.exe") is None
    assert bobreport.sanitize_python_digest_tag("/usr/bin/python3") is None
    assert bobreport.sanitize_python_digest_tag("") is None


def test_fr7022_read_python_status_field(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert bobreport.read_python_status_field(home) is None
    _write_python_status(home, python="missing")
    assert bobreport.read_python_status_field(home) == "missing"
    _write_python_status(home, python="path:python", ok=True)
    assert bobreport.read_python_status_field(home) == "path:python"
    _write_python_status(home, python=r"D:\tools\python.exe")
    assert bobreport.read_python_status_field(home) is None


def test_fr7022_publish_posts_python_missing_from_stamp(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer())
    _write_python_status(home, python="missing")
    posted: list[dict] = []
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: False)
    monkeypatch.setattr(bobreport, "read_local_opencode_pcent", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda *a, **k: None)
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        code = bobreport.publish_local_peer_fuel(
            home, MID, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    assert posted[0].get("python") == "missing"


def test_fr7022_publish_posts_source_tag_from_stamp(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer())
    _write_python_status(home, python="registry:HKLM", ok=True)
    posted: list[dict] = []
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: False)
    monkeypatch.setattr(bobreport, "read_local_opencode_pcent", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda *a, **k: None)
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        code = bobreport.publish_local_peer_fuel(
            home, MID, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert posted[0].get("python") == "registry:HKLM"


def test_fr7022_python_change_in_fingerprint():
    a = bobreport.peer_fuel_fingerprint(_peer(python="missing"))
    b = bobreport.peer_fuel_fingerprint(_peer(python="env:BOBIVERSE_PYTHON"))
    c = bobreport.peer_fuel_fingerprint(_peer())
    assert a != b
    assert a != c
