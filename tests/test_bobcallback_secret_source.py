"""#31: BobCallback (SYSTEM) must find report.secret via digest-home profile / explicit file, and say so."""
from __future__ import annotations

from pathlib import Path

import bobcallback


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(bobcallback.SECRET_ENV, "from-env")
    assert bobcallback.find_secret(tmp_path) == ("from-env", "env:BOB_REPORT_SECRET")


def test_explicit_secret_file(monkeypatch, tmp_path):
    monkeypatch.delenv(bobcallback.SECRET_ENV, raising=False)
    monkeypatch.delenv(bobcallback.SECRET_FILE_ENV, raising=False)
    sf = _write(tmp_path / "x" / "report.secret", "abc\n")
    sec, src = bobcallback.find_secret(tmp_path / "nohome", str(sf))
    assert sec == "abc" and src == str(sf)


def test_secret_file_env(monkeypatch, tmp_path):
    monkeypatch.delenv(bobcallback.SECRET_ENV, raising=False)
    sf = _write(tmp_path / "y" / "report.secret", "viaenv")
    monkeypatch.setenv(bobcallback.SECRET_FILE_ENV, str(sf))
    assert bobcallback.find_secret(tmp_path / "nohome")[0] == "viaenv"


def test_system_profile_falls_back_to_digest_home_profile(monkeypatch, tmp_path):
    """SYSTEM's Path.home() has no secret; the digest home's owning profile does."""
    monkeypatch.delenv(bobcallback.SECRET_ENV, raising=False)
    monkeypatch.delenv(bobcallback.SECRET_FILE_ENV, raising=False)
    system_home = tmp_path / "systemprofile"
    system_home.mkdir()
    monkeypatch.setattr(bobcallback.Path, "home", classmethod(lambda cls: system_home))
    admin = tmp_path / "Administrator"
    _write(admin / ".grok" / "bob" / "report.secret", "adminsecret\n")
    digest_home = admin / ".bobiverse"
    digest_home.mkdir()
    sec, src = bobcallback.find_secret(digest_home)
    assert sec == "adminsecret"
    assert src.endswith("report.secret")


def test_missing_secret_returns_empty(monkeypatch, tmp_path):
    monkeypatch.delenv(bobcallback.SECRET_ENV, raising=False)
    monkeypatch.delenv(bobcallback.SECRET_FILE_ENV, raising=False)
    monkeypatch.setattr(bobcallback.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
    assert bobcallback.find_secret(tmp_path / "nohome2" / ".bobiverse-x") == ("", "")
    assert bobcallback.load_secret(tmp_path / "nohome2" / ".bobiverse-x") == ""
