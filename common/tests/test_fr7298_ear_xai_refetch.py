"""FR #7298: SYSTEM ear retries xAI every 60s, logs attempts, keeps last-good."""
from __future__ import annotations

from datetime import datetime, timezone

import bobreport
import bobstat


def setup_function() -> None:
    bobreport.reset_pool_fetch_state()


def test_fr7298_login_expired_retries_every_60s_not_backoff():
    now = 1_700_000_000.0
    bobreport.mark_pool_fetch(
        "xai", now, ok=False, error=bobreport.XAI_GROK_LOGIN_EXPIRED, rate_limited=False
    )
    assert bobreport.pool_fetch_due("xai", now + 1.0) is False
    assert bobreport.pool_fetch_due("xai", now + 60.0) is True


def test_fr7298_429_still_backs_off():
    # FR #7471: rename retained; 429 no longer backs off past 60s.
    now = 1_700_000_000.0
    bobreport.mark_pool_fetch(
        "xai", now, ok=False, error="provider-http-429", rate_limited=True
    )
    assert bobreport.pool_fetch_due("xai", now + 1.0) is False
    assert bobreport.pool_fetch_due("xai", now + 60.0) is True



def test_fr7298_expired_login_keeps_fetched_at_advances_last_attempt():
    last = "2026-11-13T07:15:00Z"
    peer = {
        "weekly": 19,
        "weekly_known": True,
        "xai_weekly_fetched_at": last,
        "xai_weekly": {"fetched_at": last, "remaining_pct": 19},
    }
    clock = datetime(2026, 11, 14, 17, 56, tzinfo=timezone.utc)
    out = bobreport.enrich_peer_keep_last_good_xai_weekly(
        peer,
        error=bobreport.XAI_GROK_LOGIN_EXPIRED,
        now=clock,
        machine_id="marchhare",
    )
    meter = out["xai_weekly"]
    assert meter["fetched_at"] == last
    assert meter["remaining_pct"] == 19
    assert meter["error"] == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert meter["last_attempt_at"] == "2026-11-14T17:56:00Z"
    assert "sign in once on marchhare" in str(meter.get("error_action") or "")
    assert meter["fresh"] is False
    assert int(meter.get("age_s") or 0) > 120


def test_fr7298_two_failed_ticks_call_fetch_and_log(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    last = "2026-11-13T07:15:00Z"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 19,
            "weekly_known": True,
            "remaining_pct": 19,
            "xai_weekly_fetched_at": last,
            "xai_weekly": {"fetched_at": last, "remaining_pct": 19, "weekly_known": True},
        },
    )
    hits = {"n": 0}

    def fake_xai(*, now=None):
        hits["n"] += 1
        bobreport._last_xai_acquisition = {
            "identity": "live-billing",
            "read": False,
            "live": False,
            "error": bobreport.XAI_GROK_LOGIN_EXPIRED,
            "selected": True,
            "account": None,
            "auth_path": "C:/Users/Public/auth.json",
        }
        return None

    posted: list = []

    def fake_post(payload, url=""):
        posted.append(dict(payload))
        bobreport._last_post_outcome = {"http_status": 204, "ack": True, "error": None}
        return 204

    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", fake_xai)
    monkeypatch.setattr(bobreport, "post_report_json", fake_post)
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None, env=None: {
            "ok": True,
            "url": "https://example.test/bob/v1/report",
            "host": "example.test",
            "path": "/bob/v1/report",
            "source": "test",
        },
    )
    t0 = 1_700_000_000.0
    bobreport.reset_pool_fetch_state()
    assert bobreport.publish_local_peer_fuel(home, mid, force=False, now=t0) == 204
    assert bobreport.publish_local_peer_fuel(home, mid, force=False, now=t0 + 60.0) == 204
    assert hits["n"] == 2
    assert posted[0]["xai_weekly"]["fetched_at"] == last
    assert posted[1]["xai_weekly"]["fetched_at"] == last
    assert posted[0]["xai_weekly"]["last_attempt_at"] != posted[1]["xai_weekly"]["last_attempt_at"]
    line = bobreport.format_fuel_publish_diag(bobreport.last_fuel_publish_diag())
    assert "xai_attempt=" in line
    assert "grok-login-expired" in line
    assert "Bearer" not in line
    assert "password" not in line.lower()


def test_fr7298_diag_mentions_attempt_on_cached_skip():
    bobreport._last_fuel_publish_diag = {
        "xai_attempt": "cached",
        "xai_weekly_error": None,
    }
    line = bobreport.format_fuel_publish_diag(bobreport.last_fuel_publish_diag())
    # FR #7365: pool-interval skip is cached-reading (not a successful apply).
    assert "xai_attempt=cached" in line or "xai_attempt=cached-reading" in line
