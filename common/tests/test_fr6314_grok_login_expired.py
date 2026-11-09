"""FR #6314: xAI billing 401/403 -> grok-login-expired (keep last-good stale).

Other HTTP failures keep provider-http-N. Ear never rewrites auth.json.
"""
from __future__ import annotations

import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402
import bobstat  # noqa: E402


def _write_auth(path: Path, key: str = "FAKE_SESSION_KEY_FOR_TESTS_ONLY") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::test": {
                    "key": key,
                    "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
                }
            }
        ),
        encoding="utf-8",
    )


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "denied", hdrs=None, fp=None)


def test_fr6314_constant_is_distinct():
    assert bobreport.XAI_GROK_LOGIN_EXPIRED == "grok-login-expired"
    assert "401" not in bobreport.XAI_GROK_LOGIN_EXPIRED
    assert "provider-http" not in bobreport.XAI_GROK_LOGIN_EXPIRED


@pytest.mark.parametrize("code", [401, 403])
def test_fr6314_http_auth_maps_to_grok_login_expired(monkeypatch, tmp_path: Path, code: int):
    auth = tmp_path / "auth.json"
    _write_auth(auth)
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    now = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise _http_error(req.get_full_url(), code)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=now)
    assert reading is None
    acq = bobreport._last_xai_acquisition
    assert acq.get("error") == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert acq.get("live") is False
    assert "401" not in str(acq.get("error"))
    assert "403" not in str(acq.get("error"))
    assert f"provider-http-{code}" != acq.get("error")


def test_fr6314_http_500_keeps_provider_http_class(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    _write_auth(auth)
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise _http_error(req.get_full_url(), 500)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)
        )
    assert reading is None
    assert bobreport._last_xai_acquisition.get("error") == "provider-http-500"


def test_fr6314_publish_keeps_last_good_with_login_expired(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    last_at = "2026-11-09T16:34:28Z"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 19,
            "weekly_known": True,
            "pcent": {"grok-build": 19},
            "xai_weekly_fetched_at": last_at,
            "xai_weekly_source": "prior-live",
            "xai_weekly": {
                "remaining_pct": 19,
                "fetched_at": last_at,
                "source": "prior-live",
                "fresh": True,
            },
            "lastSeen": last_at,
        },
    )
    auth = tmp_path / "auth.json"
    _write_auth(auth)
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")

    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "billing" in url:
            raise _http_error(url, 401)
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

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    body = posted[0]
    assert body.get("weekly") == 19
    meter = body.get("xai_weekly") or {}
    assert meter.get("fresh") is False
    assert meter.get("error") == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert meter.get("fetched_at") == last_at
    assert meter.get("remaining_pct") == 19
    assert bobreport._last_fuel_publish_diag.get("xai_weekly_error") == (
        bobreport.XAI_GROK_LOGIN_EXPIRED
    )
