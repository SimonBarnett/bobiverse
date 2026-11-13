"""FR #7035: successful python resolve must not leave digest python=missing."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat

from test_fr7022_python_status_digest import (
    MID,
    _fake_urlopen,
    _peer,
    _write_python_status,
)


def _publish(home: Path, monkeypatch) -> dict:
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
    assert posted
    return posted[-1]


def test_fr7035_note_python_resolved_writes_source_tag(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    stamp = _write_python_status(home, python="missing")
    assert bobreport.note_python_resolved(home, "env:BOBIVERSE_PYTHON") is True
    doc = json.loads(stamp.read_text(encoding="utf-8"))
    assert doc.get("ok") is True
    assert doc.get("python") == "env:BOBIVERSE_PYTHON"
    assert "\\" not in str(doc.get("python"))
    assert bobreport.read_python_status_field(home) == "env:BOBIVERSE_PYTHON"


def test_fr7035_note_python_resolved_unlinks_when_tag_unsafe(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    stamp = _write_python_status(home, python="missing")
    assert bobreport.note_python_resolved(home, r"C:\Python\python.exe") is True
    assert not stamp.is_file()
    assert bobreport.read_python_status_field(home) is None


def test_fr7035_publish_after_resolve_never_stale_missing(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer())
    _write_python_status(home, python="missing")
    bobreport.note_python_resolved(home, "env:BOBIVERSE_PYTHON")
    body = _publish(home, monkeypatch)
    assert body.get("python") != "missing"
    assert body.get("python") == "env:BOBIVERSE_PYTHON"


def test_fr7035_irc_agent_calls_note_python_resolved_on_spawn_ok():
    root = Path(__file__).resolve().parents[1]
    agent = (root / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "note_python_resolved" in agent
    assert "FR #7035" in agent
