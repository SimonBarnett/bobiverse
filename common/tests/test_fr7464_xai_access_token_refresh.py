"""FR #7464: ear refreshes expired xAI access tokens via refresh_token."""
from __future__ import annotations

import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402
import bobstat  # noqa: E402

SLOT = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"
FAKE_ACCESS = "FAKE_ACCESS_FOR_TESTS_ONLY"
FAKE_ACCESS_NEW = "FAKE_ACCESS_REFRESHED_FOR_TESTS_ONLY"
FAKE_REFRESH = "FAKE_REFRESH_FOR_TESTS_ONLY"
FAKE_REFRESH_NEW = "FAKE_REFRESH_ROTATED_FOR_TESTS_ONLY"


def _write_auth(
    path: Path,
    *,
    access: str = FAKE_ACCESS,
    refresh: str | None = FAKE_REFRESH,
    expires_at: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict = {
        "key": access,
        "email": "operator@example.test",
        "auth_mode": "oidc",
    }
    if refresh is not None:
        entry["refresh_token"] = refresh
    if expires_at is not None:
        entry["expires_at"] = expires_at
    path.write_text(json.dumps({SLOT: entry}), encoding="utf-8")


def _credits_body(used_pct: float = 22.0) -> bytes:
    return json.dumps(
        {
            "config": {
                "creditUsagePercent": used_pct,
                "billingPeriodEnd": "2099-12-01T00:00:00Z",
            }
        }
    ).encode("utf-8")


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "denied", hdrs=None, fp=None)


def _json_resp(payload: dict):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return Resp()


def test_fr7464_expired_access_refreshes_and_fetches_fresh(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    _write_auth(auth, expires_at="2026-11-15T11:00:00Z")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    calls: list[str] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        calls.append(url)
        if "oauth2/token" in url:
            body = req.data.decode("utf-8") if req.data else ""
            assert "grant_type=refresh_token" in body
            assert "FAKE_REFRESH" in body or "refresh_token=" in body
            # Never echo tokens into assertions beyond fixture markers.
            return _json_resp(
                {
                    "access_token": FAKE_ACCESS_NEW,
                    "refresh_token": FAKE_REFRESH_NEW,
                    "expires_in": 21600,
                    "token_type": "Bearer",
                }
            )
        if "billing" in url:
            authz = req.get_header("Authorization") or ""
            assert authz == "Bearer " + FAKE_ACCESS_NEW
            return _json_resp(
                {
                    "config": {
                        "creditUsagePercent": 18.0,
                        "billingPeriodEnd": "2099-12-01T00:00:00Z",
                    }
                }
            )
        raise AssertionError("unexpected url")

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=now)
    assert reading is not None
    assert reading["remaining_pct"] == 82
    assert reading.get("fresh") is True
    acq = bobreport._last_xai_acquisition
    assert acq.get("error") is None
    assert acq.get("live") is True
    assert acq.get("refreshed") is True
    assert any("oauth2/token" in u for u in calls)
    saved = json.loads(auth.read_text(encoding="utf-8"))
    entry = saved[SLOT]
    assert entry["key"] == FAKE_ACCESS_NEW
    assert entry["refresh_token"] == FAKE_REFRESH_NEW
    assert entry["expires_at"].startswith("2026-11-15T18:")
    blob = auth.read_text(encoding="utf-8")
    for marker in ("password=", "Bearer "):
        assert marker not in blob


def test_fr7464_refresh_rejected_reports_grok_login_expired_keeps_last_good(
    monkeypatch, tmp_path: Path
):
    home = tmp_path / "home"
    home.mkdir()
    mid = "box-a"
    last_at = "2026-11-15T11:54:40Z"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 41,
            "weekly_known": True,
            "xai_weekly_fetched_at": last_at,
            "xai_weekly": {
                "remaining_pct": 41,
                "fetched_at": last_at,
                "source": "prior-live",
                "fresh": True,
            },
            "lastSeen": last_at,
        },
    )
    auth = tmp_path / "auth.json"
    _write_auth(auth, expires_at="2026-11-15T11:53:57Z")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "oauth2/token" in url:
            raise _http_error(url, 400)
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
    body = posted[0]
    meter = body.get("xai_weekly") or {}
    assert meter.get("error") == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert meter.get("fresh") is False
    assert meter.get("remaining_pct") == 41
    assert meter.get("fetched_at") == last_at
    assert "sign in once" in str(meter.get("error_action") or "")
    # Refresh rejected: auth.json access key unchanged (no partial write).
    saved = json.loads(auth.read_text(encoding="utf-8"))
    assert saved[SLOT]["key"] == FAKE_ACCESS


def test_fr7464_refresh_ahead_of_expiry_under_lead_window(monkeypatch, tmp_path: Path):
    """Machines with no seat stay fresh past 6h: refresh when under 10 min remain."""
    auth = tmp_path / "auth.json"
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    # Access still valid for 5 minutes — under the 10-minute lead.
    _write_auth(
        auth, expires_at=(now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    refreshed = {"n": 0}

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "oauth2/token" in url:
            refreshed["n"] += 1
            return _json_resp(
                {
                    "access_token": FAKE_ACCESS_NEW,
                    "expires_in": 21600,
                    "token_type": "Bearer",
                }
            )
        if "billing" in url:
            return _json_resp(
                {
                    "config": {
                        "creditUsagePercent": 10.0,
                        "billingPeriodEnd": "2099-12-01T00:00:00Z",
                    }
                }
            )
        raise AssertionError(url)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=now)
    assert reading is not None
    assert refreshed["n"] == 1
    assert bobreport._last_xai_acquisition.get("refreshed") is True
    # Simulate next fuel cycle 6h later with the rewritten expires_at still valid.
    later = now + timedelta(hours=6)
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading2 = bobreport.fetch_live_xai_weekly(now=later)
    assert reading2 is not None
    # Second cycle: still under lead relative to new 6h expiry? later is exactly
    # at original+6h; new expires_at is now+6h from first refresh → at `later`
    # remain ~0, so another refresh is expected (healthy churn, not stale).
    assert refreshed["n"] >= 2


def test_fr7464_ensure_maps_refresh_rejected_to_login_expired(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    _write_auth(auth, expires_at="2020-01-01T00:00:00Z")

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise _http_error(req.get_full_url(), 401)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        token, err, label, did = bobreport.ensure_grok_auth_access_token(auth, now=now)
    assert token is None
    assert err == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert did is False
    assert label == "operator@example.test"


def test_fr7464_no_secrets_in_acquisition_or_auth_write(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    _write_auth(auth, expires_at="2020-01-01T00:00:00Z")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "oauth2/token" in url:
            return _json_resp(
                {"access_token": FAKE_ACCESS_NEW, "expires_in": 100, "token_type": "Bearer"}
            )
        return _json_resp(
            {
                "config": {
                    "creditUsagePercent": 1.0,
                    "billingPeriodEnd": "2099-12-01T00:00:00Z",
                }
            }
        )

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        bobreport.fetch_live_xai_weekly(now=now)
    acq = json.dumps(bobreport._last_xai_acquisition)
    assert FAKE_ACCESS_NEW not in acq
    assert FAKE_REFRESH not in acq
    assert "Bearer " not in acq


def test_fr7464_refresh_works_when_process_is_localsystem(monkeypatch, tmp_path: Path):
    """SYSTEM ear (ircBob) refreshes the interactive auth path it already reads."""
    auth = tmp_path / "Users" / "Operator" / ".grok" / "auth.json"
    now = datetime(2026, 11, 15, 13, 0, tzinfo=timezone.utc)
    _write_auth(auth, expires_at="2026-11-15T11:53:57Z")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_HOME", raising=False)
    monkeypatch.setenv("BOB_GROK_WEEKLY_USER_HOME", str(auth.parents[1]))
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(
        bobreport,
        "_interactive_grok_user_home",
        lambda: auth.parents[1],
    )

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "oauth2/token" in url:
            return _json_resp(
                {
                    "access_token": FAKE_ACCESS_NEW,
                    "refresh_token": FAKE_REFRESH_NEW,
                    "expires_in": 21600,
                    "token_type": "Bearer",
                }
            )
        if "billing" in url:
            return _json_resp(
                {
                    "config": {
                        "creditUsagePercent": 5.0,
                        "billingPeriodEnd": "2099-12-01T00:00:00Z",
                    }
                }
            )
        raise AssertionError(url)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=now)
    assert reading is not None
    assert reading["remaining_pct"] == 95
    assert bobreport._last_xai_acquisition.get("refreshed") is True
    saved = json.loads(auth.read_text(encoding="utf-8"))
    assert saved[SLOT]["key"] == FAKE_ACCESS_NEW
