"""FR #7400: cached xAI weekly is bound to the account it was fetched for."""
from __future__ import annotations

from datetime import datetime, timezone

import bobreport


NOW = datetime(2026, 11, 14, 22, 30, tzinfo=timezone.utc)
ACCT_A = "si@ntsa.uk"
ACCT_B = "social@smartcatalogue.uk"


def _peer_a_65() -> dict:
    last = "2026-11-14T12:00:00Z"
    return {
        "ok": True,
        "id": "redqueen",
        "weekly": 65,
        "weekly_known": True,
        "remaining_pct": 65,
        "grok_account": ACCT_A,
        "xai_weekly_fetched_at": last,
        "xai_weekly_used_pct": 35,
        "xai_weekly": {
            "provider": "xai",
            "window": "weekly",
            "remaining_pct": 65,
            "used_pct": 35,
            "fetched_at": last,
            "account": ACCT_A,
            "fresh": True,
        },
        "pcent": {"grok-build": 65},
    }


def test_fr7400_account_switch_fetch_fail_unknown_not_old_pct():
    peer = _peer_a_65()
    out = bobreport.enrich_peer_keep_last_good_xai_weekly(
        peer,
        error="live-fetch-failed",
        now=NOW,
        machine_id="redqueen",
        current_account=ACCT_B,
    )
    meter = out["xai_weekly"]
    assert meter.get("remaining_pct") is None
    assert out.get("weekly") is None
    assert out.get("weekly_known") is False
    assert (out.get("pcent") or {}).get("grok-build") is None
    assert meter.get("account") == ACCT_B
    assert out.get("grok_account") == ACCT_B
    assert meter.get("error")
    assert meter.get("fresh") is False
    assert meter.get("used_pct") is None


def test_fr7400_same_account_fetch_fail_keeps_stale_pct():
    peer = _peer_a_65()
    out = bobreport.enrich_peer_keep_last_good_xai_weekly(
        peer,
        error=bobreport.XAI_GROK_LOGIN_EXPIRED,
        now=NOW,
        machine_id="redqueen",
        current_account=ACCT_A,
    )
    meter = out["xai_weekly"]
    assert meter.get("remaining_pct") == 65
    assert out.get("weekly") == 65
    assert out.get("weekly_known") is True
    assert meter.get("fetched_at") == "2026-11-14T12:00:00Z"
    assert meter.get("fresh") is False
    assert meter.get("account") == ACCT_A
    assert "sign in once" in str(meter.get("error_action") or "")


def test_fr7400_stamp_does_not_relabel_foreign_cache():
    peer = _peer_a_65()
    bobreport._last_xai_acquisition = {
        "selected": True,
        "account": ACCT_B,
        "error": "live-fetch-failed",
    }
    stamped = bobreport.stamp_peer_xai_account_from_acquisition(peer)
    meter = stamped.get("xai_weekly") or {}
    assert meter.get("remaining_pct") in (None, 65)
    # Must not publish A's 65% under B.
    if meter.get("account") == ACCT_B:
        assert meter.get("remaining_pct") is None
        assert stamped.get("weekly") is None
    else:
        assert meter.get("account") == ACCT_A
        assert meter.get("remaining_pct") == 65
