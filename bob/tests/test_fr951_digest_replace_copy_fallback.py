"""FR #951: when os.replace stays Access denied, fall back to copyfile over digest.json."""
from __future__ import annotations

import os
from pathlib import Path

import bobreport
import registered_machines
import pytest


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    registered_machines.save_registered(tmp_path, {"marchhare"})
    return tmp_path


def test_replace_falls_back_to_copyfile_when_winerror_5_persists(tmp_path, monkeypatch):
    src = tmp_path / "digest.json.22204.09faa6ef1cf3.tmp"
    dst = tmp_path / "digest.json"
    src.write_text('{"v":1}\n', encoding="utf-8")
    dst.write_text("{}\n", encoding="utf-8")
    calls = {"replace": 0, "copy": 0}
    real_copy = bobreport.shutil.copyfile

    def always_denied(s, d):
        calls["replace"] += 1
        e = OSError(5, "Access is denied")
        e.winerror = 5
        raise e

    def spy_copy(s, d):
        calls["copy"] += 1
        return real_copy(s, d)

    monkeypatch.setattr(bobreport.os, "replace", always_denied)
    monkeypatch.setattr(bobreport.shutil, "copyfile", spy_copy)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0))
    bobreport._replace_with_retry(src, dst)
    assert calls["replace"] >= 2
    assert calls["copy"] == 1
    assert dst.read_text(encoding="utf-8") == '{"v":1}\n'


def test_save_digest_survives_persistent_winerror_5_via_copy(home, monkeypatch):
    """Webhook report route shape: unique tmp -> replace Access denied -> copy wins."""
    real_replace = os.replace

    def denied_replace(s, d):
        e = OSError(5, "Access is denied")
        e.winerror = 5
        raise e

    monkeypatch.setattr(bobreport.os, "replace", denied_replace)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0,))
    doc = bobreport.load_digest(home)
    doc["ts"] = "2026-10-03T15:11:15Z"
    bobreport.save_digest(home, doc)
    assert bobreport.digest_path(home).is_file()
    loaded = bobreport.load_digest(home)
    assert loaded.get("ts") == "2026-10-03T15:11:15Z"
    assert not list(home.glob("digest.json.*.tmp"))


def test_replace_still_raises_when_copy_also_fails(tmp_path, monkeypatch):
    src = tmp_path / "a.tmp"
    dst = tmp_path / "a"
    src.write_text("x", encoding="utf-8")

    def denied_replace(s, d):
        e = OSError(5, "Access is denied")
        e.winerror = 5
        raise e

    def denied_copy(s, d):
        e = OSError(5, "Access is denied")
        e.winerror = 5
        raise e

    monkeypatch.setattr(bobreport.os, "replace", denied_replace)
    monkeypatch.setattr(bobreport.shutil, "copyfile", denied_copy)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0,))
    with pytest.raises(OSError) as ei:
        bobreport._replace_with_retry(src, dst)
    assert getattr(ei.value, "winerror", None) == 5
