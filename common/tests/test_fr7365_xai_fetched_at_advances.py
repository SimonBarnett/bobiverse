"""FR #7365: live xAI apply advances fetched_at; diag ok only when applied."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


def _peer(mid: str, *, fetched_at: str, weekly: int = 40) -> dict:
    return {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": weekly,
        "weekly_known": True,
        "pcent": {"grok-build": weekly},
        "xai_weekly_fetched_at": fetched_at,
        "xai_weekly_source": "prior-live",
        "xai_weekly": {
            "remaining_pct": weekly,
            "fetched_at": fetched_at,
            "source": "prior-live",
            "fresh": True,
            "weekly_known": True,
        },
        "lastSeen": fetched_at,
    }


def test_fr7365_classify_attempt_reasons():
    assert bobreport.classify_xai_weekly_attempt(None, err="auth-missing") == "auth-missing"
    assert (
        bobreport.classify_xai_weekly_attempt(
            {"weekly_known": False, "fresh": True}, err=None
        )
        == "not-known"
    )
    assert (
        bobreport.classify_xai_weekly_attempt(
            {"weekly_known": True, "fresh": False}, err=None
        )
        == "not-fresh"
    )
    assert (
        bobreport.classify_xai_weekly_attempt(
            {"weekly_known": True, "fresh": True}, applied=True
        )
        == "ok"
    )


def test_fr7365_fresh_reading_advances_fetched_at(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    old = "2026-11-14T20:52:56Z"
    bobstat.write_peer(home, _peer(mid, fetched_at=old, weekly=40))
    clock = datetime(2026, 11, 14, 20, 58, 0, tzinfo=timezone.utc)
    reading = {
        "remaining_pct": 41,
        "used_pct": 59,
        "weekly_known": True,
        "fresh": True,
        "fetched_at": old,  # provider/cache stamped old — live apply must use fetch clock
        "source": bobreport.XAI_BILLING_SOURCE,
        "period_end": None,
        "error": None,
    }
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda now=None: reading)
    monkeypatch.setattr(
        bobreport,
        "_last_xai_acquisition",
        {"identity": "live-billing", "read": True, "live": True, "error": None},
    )
    posted: list[dict] = []

    def fake_post(payload, url=""):
        posted.append(dict(payload))
        bobreport._last_post_outcome = {"http_status": 204, "ack": True, "error": None}
        return 204

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
    bobreport.reset_pool_fetch_state()
    code = bobreport.publish_local_peer_fuel(
        home, mid, force=True, now=clock.timestamp(), url="https://example.test/bob/v1/report"
    )
    assert code == 204
    assert posted
    meter = posted[0].get("xai_weekly") or {}
    assert meter.get("fetched_at") == "2026-11-14T20:58:00Z"
    assert posted[0].get("xai_weekly_fetched_at") == "2026-11-14T20:58:00Z"
    assert meter.get("fresh") is True
    assert bobreport._last_fuel_publish_diag.get("xai_attempt") == "ok"
    disk = bobstat.read_peer(home, mid) or {}
    assert disk.get("xai_weekly_fetched_at") == "2026-11-14T20:58:00Z"


def test_fr7365_not_fresh_keeps_fetched_at_and_diag(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    old = "2026-11-14T20:52:56Z"
    bobstat.write_peer(home, _peer(mid, fetched_at=old, weekly=40))
    clock = datetime(2026, 11, 14, 20, 58, 0, tzinfo=timezone.utc)
    reading = {
        "remaining_pct": 40,
        "used_pct": 60,
        "weekly_known": True,
        "fresh": False,
        "fetched_at": "2026-11-14T20:58:00Z",
        "source": "cached-proxy",
        "error": None,
    }
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda now=None: reading)
    monkeypatch.setattr(
        bobreport,
        "_last_xai_acquisition",
        {"identity": "live-billing", "read": True, "live": True, "error": None},
    )
    posted: list[dict] = []

    def fake_post(payload, url=""):
        posted.append(dict(payload))
        bobreport._last_post_outcome = {"http_status": 204, "ack": True, "error": None}
        return 204

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
    bobreport.reset_pool_fetch_state()
    code = bobreport.publish_local_peer_fuel(
        home, mid, force=True, now=clock.timestamp(), url="https://example.test/bob/v1/report"
    )
    assert code == 204
    meter = posted[0].get("xai_weekly") or {}
    assert meter.get("fetched_at") == old
    assert meter.get("fresh") is False
    assert bobreport._last_fuel_publish_diag.get("xai_attempt") == "not-fresh"
    assert bobreport._last_fuel_publish_diag.get("xai_attempt") != "ok"


def test_fr7365_cached_provider_timestamp_overridden_on_live_apply():
    peer = _peer("flamingo", fetched_at="2026-11-14T20:00:00Z", weekly=10)
    reading = {
        "remaining_pct": 12,
        "used_pct": 88,
        "weekly_known": True,
        "fresh": True,
        "fetched_at": "2026-11-01T00:00:00Z",
        "source": bobreport.XAI_BILLING_SOURCE,
        "error": None,
    }
    clock = datetime(2026, 11, 14, 21, 0, 0, tzinfo=timezone.utc)
    out = bobreport.apply_live_xai_weekly_reading(peer, reading, now=clock)
    assert out.get("xai_weekly_fetched_at") == "2026-11-14T21:00:00Z"
    assert (out.get("xai_weekly") or {}).get("fetched_at") == "2026-11-14T21:00:00Z"
    assert (out.get("xai_weekly") or {}).get("fresh") is True
    assert out.get("weekly") == 12
