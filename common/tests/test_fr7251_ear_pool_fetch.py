"""FR #7251: SYSTEM ear fetches every pool every 60s and stamps fetched_at."""
from __future__ import annotations

from datetime import datetime, timezone

import bobreport
import copilot_dispatch as cd


def setup_function() -> None:
    bobreport.reset_pool_fetch_state()


def test_ear_pool_fetch_constant_is_60():
    assert bobreport.EAR_POOL_FETCH_S == 60.0
    assert cd.CACHE_S == bobreport.EAR_POOL_FETCH_S
    assert bobreport.DEFAULT_OPENCODE_FUEL_CACHE_S == bobreport.EAR_POOL_FETCH_S


def test_pool_fetch_due_every_60s_not_sooner():
    now = 1_700_000_000.0
    assert bobreport.pool_fetch_due("copilot", now) is True
    bobreport.mark_pool_fetch("copilot", now, ok=True)
    assert bobreport.pool_fetch_due("copilot", now + 59.0) is False
    assert bobreport.pool_fetch_due("copilot", now + 60.0) is True


def test_rate_limit_backoff_skips_until_later():
    now = 1_700_000_000.0
    bobreport.mark_pool_fetch("xai", now, ok=False, error="provider-http-429", rate_limited=True)
    assert bobreport.pool_fetch_due("xai", now + 1.0) is False
    assert bobreport.pool_fetch_due("xai", now + bobreport.EAR_POOL_FETCH_S * 2 + 1.0) is True


def test_xai_failure_stamps_last_attempt_keeps_fetched_at():
    last = "2026-11-14T12:00:00Z"
    peer = {
        "weekly": 19,
        "weekly_known": True,
        "xai_weekly_fetched_at": last,
        "xai_weekly": {"fetched_at": last, "remaining_pct": 19},
    }
    clock = datetime(2026, 11, 14, 12, 5, tzinfo=timezone.utc)
    out = bobreport.enrich_peer_keep_last_good_xai_weekly(
        peer, error="provider-http-429", now=clock
    )
    meter = out["xai_weekly"]
    assert meter["fetched_at"] == last
    assert meter["fresh"] is False
    assert meter["error"] == "provider-http-429"
    assert meter["last_attempt_at"] == "2026-11-14T12:05:00Z"
    assert meter["period_end"] != meter["last_attempt_at"]


def test_billing_fetched_at_is_clock_not_period_end():
    doc = {
        "config": {
            "creditUsagePercent": 10,
            "currentPeriod": {"end": "2026-11-20T00:00:00Z"},
        }
    }
    clock = datetime(2026, 11, 14, 15, 1, tzinfo=timezone.utc)
    reading = bobreport.parse_xai_billing_credits_response(doc, now=clock)
    assert reading is not None
    assert reading["fetched_at"] == "2026-11-14T15:01:00Z"
    assert reading["period_end"] == "2026-11-20T00:00:00Z"
    assert reading["fetched_at"] != reading["period_end"]


def test_two_ticks_60s_apart_new_fetched_at_per_pool(tmp_path, monkeypatch):
    """Two publish cycles 60s apart must advance fetched_at on ear-owned pools.

    FR #7255 / #7289: Copilot / OpenCode / Cursor are Jeeves fleet_pools.
    """
    home = tmp_path / "home"
    home.mkdir()
    mid = "flamingo"
    import bobstat

    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 40,
            "weekly_known": True,
            "remaining_pct": 40,
            "pcent": {"grok-chat": 40, "grok-build": 40},
            "cursor_pools": [{"id": "grok-weekly", "remaining": 40}],
        },
    )
    posted: list[dict] = []

    def fake_post(payload, url=""):
        posted.append(dict(payload))
        bobreport._last_post_outcome = {"http_status": 204, "ack": True, "error": None}
        return 204

    t0 = 1_700_000_000.0
    clock = {"n": 0}

    def fake_xai(*, now=None):
        if now is None:
            epoch = t0 + clock["n"] * 60.0
        elif hasattr(now, "timestamp"):
            epoch = float(now.timestamp())
        else:
            epoch = float(now)
        iso = bobreport.iso_utc_from_epoch(epoch)
        bobreport._last_xai_acquisition = {
            "identity": "live-billing",
            "read": True,
            "live": True,
            "error": None,
            "selected": True,
            "account": None,
        }
        return {
            "remaining_pct": 40,
            "used_pct": 60,
            "weekly_known": True,
            "period_end": "2026-11-20T00:00:00Z",
            "fetched_at": iso,
            "source": "cli-chat-proxy:/v1/billing?format=credits",
            "fresh": True,
        }

    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", fake_xai)
    monkeypatch.setattr(bobstat, "load_cursor_usage_doc", lambda: {"ok": True, "remaining_pct": 40})
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
    clock["n"] = 0
    assert bobreport.publish_local_peer_fuel(home, mid, force=True, now=t0) == 204
    clock["n"] = 1
    assert bobreport.publish_local_peer_fuel(home, mid, force=True, now=t0 + 60.0) == 204
    assert len(posted) == 2
    a, b = posted[0], posted[1]
    assert a["xai_weekly"]["fetched_at"] != b["xai_weekly"]["fetched_at"]
    assert "2026-11-20T00:00:00Z" != b["xai_weekly"]["fetched_at"]
    # FR #7255 / #7289: ear must not publish Copilot / OpenCode / Cursor (Jeeves fleet).
    assert "copilot" not in a and "copilot" not in b
    assert "remaining_fetched_at" not in a and "remaining_fetched_at" not in b
    assert a.get("opencode_fetched_at") in (None, "")
    assert b.get("opencode_fetched_at") in (None, "")
