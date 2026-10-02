"""FR #36 / #35 / #37 / #38: digest.json.tmp WinError 2 / 5 / 32 on bobcallback report.

Pre-#51 writers all shared one fixed ``digest.json.tmp``; concurrent replace then failed with
FileNotFoundError (WinError 2) when another writer had already moved the tmp, or with sharing /
access-denied errors. save_digest must never use that fixed name, and must survive a tmp that
vanishes between write and replace (rewrite once).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import bobreport
import registered_machines


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    return tmp_path


def test_fr36_save_digest_never_uses_fixed_digest_json_tmp_name(home, monkeypatch):
    seen: list[str] = []
    real = bobreport._replace_with_retry

    def spy(src, dst):
        seen.append(Path(src).name)
        return real(src, dst)

    monkeypatch.setattr(bobreport, "_replace_with_retry", spy)
    for _ in range(5):
        bobreport.save_digest(home, bobreport.load_digest(home))
    assert seen
    assert all(n.startswith("digest.json.") and n.endswith(".tmp") for n in seen)
    assert "digest.json.tmp" not in seen
    assert not (home / "digest.json.tmp").exists()


def test_fr36_save_digest_rewrites_when_tmp_vanishes_before_replace(home, monkeypatch):
    """WinError 2: source tmp gone between write_text and os.replace — rewrite once, succeed."""
    calls = {"n": 0}
    real = os.replace

    def vanish_once(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            Path(src).unlink(missing_ok=True)
            raise FileNotFoundError(2, "The system cannot find the file specified", str(src))
        return real(src, dst)

    monkeypatch.setattr(bobreport.os, "replace", vanish_once)
    bobreport.save_digest(home, bobreport.load_digest(home))
    assert calls["n"] == 2
    assert bobreport.digest_path(home).is_file()
    assert not list(home.glob("digest.json.*.tmp"))


def test_fr36_file_not_found_on_replace_is_not_treated_as_sharing_retry_only(tmp_path, monkeypatch):
    """Sharing retries alone cannot fix a missing src; save_digest must rewrite (covered above).

    _replace_with_retry still raises FileNotFoundError immediately (no pointless backoff).
    """
    src = tmp_path / "a.tmp"
    src.write_text("x", encoding="utf-8")
    src.unlink()

    def missing(s, d):
        raise FileNotFoundError(2, "gone", str(s))

    monkeypatch.setattr(bobreport.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        bobreport._replace_with_retry(tmp_path / "a.tmp", tmp_path / "a")
