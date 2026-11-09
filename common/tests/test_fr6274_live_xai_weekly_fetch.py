"""FR #6274: ear acquires Grok/xAI weekly live at fetch time.

Fixtures use used=28 / remaining=72 and last-good=19 — never 82/74/43/75/35.
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
import bobstat  # noqa: E402


def _credits_body(used_pct: float = 28.0) -> bytes:
    doc = {
        "config": {
            "currentPeriod": {
                "type": "USAGE_PERIOD_TYPE_WEEKLY",
                "start": "2026-11-08T12:00:00Z",
                "end": "2026-11-15T12:00:00Z",
            },
            "creditUsagePercent": used_pct,
            "billingPeriodEnd": "2026-11-15T12:00:00Z",
            "isUnifiedBillingUser": True,
        }
    }
    return json.dumps(doc).encode("utf-8")


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


def _billing_log(used_pct: float = 39.0) -> str:
    return (
        '{"ts":"2026-11-08T15:40:00Z","msg":"billing: fetched credits config",'
        '"ctx":{"config":{"currentPeriod":{"type":"USAGE_PERIOD_TYPE_WEEKLY",'
        '"end":"2026-11-16T12:00:00Z"},"creditUsagePercent":%s}}}\n' % used_pct
    )


def test_fr6274_parse_credits_maps_used_to_remaining():
    now = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
    reading = bobreport.parse_xai_billing_credits_response(
        json.loads(_credits_body(28.0)), now=now
    )
    assert reading is not None
    assert reading["used_pct"] == 28
    assert reading["remaining_pct"] == 72
    assert reading["weekly_known"] is True
    assert reading["fresh"] is True
    assert reading["source"] == bobreport.XAI_BILLING_SOURCE
    assert reading["fetched_at"] == "2026-11-09T08:00:00Z"
    assert reading["period_end"] == "2026-11-15T12:00:00Z"


def test_fr6274_live_fetch_success(monkeypatch, tmp_path: Path):
    auth = tmp_path / "Users" / "FleetAdmin" / ".grok" / "auth.json"
    _write_auth(auth)
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    now = datetime(2026, 11, 9, 8, 5, tzinfo=timezone.utc)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        assert "billing?format=credits" in url
        authz = req.get_header("Authorization") or req.headers.get("Authorization")
        assert authz == "Bearer FAKE_SESSION_KEY_FOR_TESTS_ONLY"

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _credits_body(28.0)

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=now)
    assert reading is not None
    assert reading["remaining_pct"] == 72
    assert reading["used_pct"] == 28
    assert reading["fresh"] is True
    assert bobreport._last_xai_acquisition["identity"] == "live-billing"
    assert bobreport._last_xai_acquisition["live"] is True


def test_fr6274_provider_error_keeps_last_good(monkeypatch, tmp_path: Path):
    import urllib.error

    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    last_at = "2026-11-09T06:00:00Z"
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
            raise urllib.error.HTTPError(url, 500, "boom", hdrs=None, fp=None)
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
    assert body.get("weekly_known") is True
    meter = body.get("xai_weekly") or {}
    assert meter.get("fresh") is False
    assert meter.get("error")
    assert "500" in str(meter.get("error"))
    assert meter.get("fetched_at") == last_at
    assert meter.get("remaining_pct") == 19
    assert bobreport._last_fuel_publish_diag.get("xai_weekly_error")


def test_fr6274_stale_log_not_posted_as_fresh(monkeypatch, tmp_path: Path):
    """Passive unified.jsonl must not become a fresh weekly post (FR #6274)."""
    import urllib.error

    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    last_at = "2026-11-09T06:00:00Z"
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
            "lastSeen": last_at,
        },
    )
    user = tmp_path / "Users" / "FleetAdmin"
    log = user / ".grok" / "logs" / "unified.jsonl"
    log.parent.mkdir(parents=True)
    # Stale log would parse as remaining 61 (used 39) — must not win over last-good.
    log.write_text(_billing_log(39.0), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_WEEKLY_USER_HOME", str(user))
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")

    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "billing" in url:
            raise urllib.error.URLError("no-live")
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
    # Must keep last-good 19; must NOT post stale-log 61 as fresh.
    assert body.get("weekly") == 19
    assert body.get("weekly") != 61
    meter = body.get("xai_weekly") or {}
    assert meter.get("fresh") is False
    assert meter.get("fetched_at") == last_at
    assert meter.get("error")
