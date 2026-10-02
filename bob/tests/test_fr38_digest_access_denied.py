"""FR #38: bobcallback report WinError 5 Access denied on digest.json.tmp -> digest.json.

Same fixed-tmp collision class as #35/#36/#37. Unique tmp (#51) + replace retry on WinError 5
must keep the report route green under AV / indexer locks on the target digest.json.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import bobreport
import registered_machines


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    registered_machines.save_registered(tmp_path, {"marchhare"})
    return tmp_path


def test_fr38_replace_retries_winerror_5_then_succeeds(tmp_path, monkeypatch):
    src = tmp_path / "digest.json.1.abc.tmp"
    dst = tmp_path / "digest.json"
    src.write_text("{}\n", encoding="utf-8")
    calls = {"n": 0}
    real = os.replace

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] < 3:
            e = OSError(5, "Access is denied")
            e.winerror = 5
            raise e
        return real(s, d)

    monkeypatch.setattr(bobreport.os, "replace", flaky)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0, 0.0, 0.0))
    bobreport._replace_with_retry(src, dst)
    assert calls["n"] == 3
    assert dst.read_text(encoding="utf-8") == "{}\n"


def test_fr38_save_digest_survives_transient_winerror_5(home, monkeypatch):
    calls = {"n": 0}
    real = os.replace

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] == 1:
            e = OSError(5, "Access is denied")
            e.winerror = 5
            raise e
        return real(s, d)

    monkeypatch.setattr(bobreport.os, "replace", flaky)
    monkeypatch.setattr(bobreport, "_REPLACE_RETRY_DELAYS", (0.0, 0.0))
    bobreport.save_digest(home, bobreport.load_digest(home))
    assert calls["n"] >= 2
    assert bobreport.digest_path(home).is_file()
    assert not (home / "digest.json.tmp").exists()
    assert not list(home.glob("digest.json.*.tmp"))
