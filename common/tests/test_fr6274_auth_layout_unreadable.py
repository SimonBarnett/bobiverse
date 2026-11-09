"""FR #6274 reopen: real auth.json layout + auth-file-unreadable vs auth-key-missing.

Fixtures use FAKE_ placeholders only. Layout mirrors Grok CLI issuer::client_id map
with entry.key (flamingo field names). Never 82/74/43/75/35.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def _flamingo_shaped_auth(key: str = "FAKE_SESSION_KEY_FOR_TESTS_ONLY") -> dict:
    """Field names observed on a live Grok CLI auth.json (values fake)."""
    return {
        "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828": {
            "auth_mode": "oidc",
            "coding_data_retention_opt_out": False,
            "create_time": "2026-11-01T00:00:00Z",
            "email": "fake@example.test",
            "expires_at": "2099-01-01T00:00:00Z",
            "first_name": "Fake",
            "key": key,
            "oidc_client_id": "b1a00492-073a-47ea-816f-4c329264a828",
            "oidc_issuer": "https://auth.x.ai",
            "principal_id": "fake-principal",
            "principal_type": "User",
            "profile_image_asset_id": "",
            "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
            "team_id": "",
            "user_id": "fake-user",
        }
    }


def test_fr6274_flamingo_layout_loads_key(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(_flamingo_shaped_auth()), encoding="utf-8")
    token, err = bobreport.load_grok_auth_bearer(path)
    assert err is None
    assert token == "FAKE_SESSION_KEY_FOR_TESTS_ONLY"


def test_fr6274_access_token_alias_loads(tmp_path: Path):
    """OIDC-style access_token is accepted when key is absent."""
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::test": {
                    "access_token": "FAKE_ACCESS_TOKEN_ONLY",
                    "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
                    "expires_at": "2099-06-01T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    token, err = bobreport.load_grok_auth_bearer(path)
    assert err is None
    assert token == "FAKE_ACCESS_TOKEN_ONLY"


def test_fr6274_auth_file_unreadable_diag(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(_flamingo_shaped_auth()), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)

    def boom(self, *a, **k):
        raise PermissionError(13, "Access is denied", str(self))

    # LocalSystem often sees the path (is_file) but cannot read ACL-protected auth.json.
    with mock.patch.object(Path, "read_text", boom):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
        )
    assert reading is None
    assert bobreport._last_xai_acquisition.get("error") == "auth-file-unreadable"
    assert bobreport._last_xai_acquisition.get("identity") == "explicit-auth"


def test_fr6274_auth_key_missing_when_readable(tmp_path: Path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::test": {
                    "email": "fake@example.test",
                    "first_name": "Fake",
                    "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    reading = bobreport.fetch_live_xai_weekly(
        now=datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
    )
    assert reading is None
    assert bobreport._last_xai_acquisition.get("error") == "auth-key-missing"


def test_fr6274_prefer_unexpired_entry(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    token, err = bobreport.load_grok_auth_bearer(path)
    assert err is None
    assert token == "FAKE_LIVE_KEY"


def test_fr6274_skip_api_key_slot_for_session(tmp_path: Path):
    """xai::api_key profile slots are not the interactive session bearer."""
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "xai::api_key": {"key": "FAKE_API_KEY_SLOT"},
                "https://auth.x.ai::session": {
                    "key": "FAKE_SESSION_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    token, err = bobreport.load_grok_auth_bearer(path)
    assert err is None
    assert token == "FAKE_SESSION_KEY"