"""MRB #6277 hostile: auth-file-bad-json must reach fetch acquisition diag.

Fixtures use FAKE_ placeholders only. Never 82/74/43/75/35.
"""
from __future__ import annotations

import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def test_mrb6277_fetch_auth_file_bad_json(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    reading = bobreport.fetch_live_xai_weekly(
        now=datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    )
    assert reading is None
    assert bobreport._last_xai_acquisition.get("error") == "auth-file-bad-json"
    assert bobreport._last_xai_acquisition.get("identity") == "explicit-auth"


def test_mrb6277_load_grok_auth_bearer_bad_json(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text("[1, 2, truncated", encoding="utf-8")
    token, err = bobreport.load_grok_auth_bearer(path)
    assert token is None
    assert err == "auth-file-bad-json"


def test_mrb6277_auth_entry_bearer_loop_var_is_name():
    """Ruff F402: loop must not shadow dataclasses.field."""
    src = inspect.getsource(bobreport._auth_entry_bearer)
    assert 'for name in ("key", "access_token")' in src
    assert "for field in" not in src
