"""MRB #7032 hostile pins for FR #7022 digest python wire."""
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


def test_mrb7032_builder_drops_path_python():
    body = bobreport.build_peer_fuel_merge_payload(
        _peer(python=r"C:\Python\python.exe"), MID
    )
    assert body is not None
    assert "python" not in body


def test_mrb7032_fingerprint_includes_python_key():
    fp = bobreport.peer_fuel_fingerprint(_peer(python="missing"))
    assert "python=missing" in fp


def test_mrb7032_publish_omits_python_without_stamp(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer())
    posted = []
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: False)
    monkeypatch.setattr(bobreport, "read_local_opencode_pcent", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda *a, **k: None)
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        code = bobreport.publish_local_peer_fuel(
            home, MID, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert "python" not in posted[0]


def test_mrb7032_python_flip_posts_without_force(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer())
    _write_python_status(home, python="missing")
    posted = []
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: False)
    monkeypatch.setattr(bobreport, "read_local_opencode_pcent", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda *a, **k: None)
    url = "https://example.test/bob/v1/report"
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        assert bobreport.publish_local_peer_fuel(home, MID, force=True, url=url) == 204
        _write_python_status(home, python="env:BOBIVERSE_PYTHON", ok=True)
        assert bobreport.publish_local_peer_fuel(home, MID, force=False, url=url) == 204
    assert posted[-1].get("python") == "env:BOBIVERSE_PYTHON"
