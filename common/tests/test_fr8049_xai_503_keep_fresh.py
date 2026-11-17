"""FR #8049: ear keeps last-good fresh on one transient 503; logs endpoint source."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def setup_function() -> None:
    bobreport.reset_pool_fetch_state()


def _peer_good(fetched_at: str) -> dict:
    return {
        "weekly": 97,
        "weekly_known": True,
        "period_end": "2026-11-22T19:28:11Z",
        "xai_weekly_fetched_at": fetched_at,
        "xai_weekly_source": bobreport.XAI_BILLING_SOURCE,
        "xai_weekly": {
            "remaining_pct": 97,
            "period_end": "2026-11-22T19:28:11Z",
            "fetched_at": fetched_at,
            "account": "social@clubmadeira.uk",
            "fresh": True,
            "source": bobreport.XAI_BILLING_SOURCE,
        },
        "grok_account": "social@clubmadeira.uk",
    }


def test_fr8049_one_503_keeps_fresh_within_stale_window():
    clock = datetime(2026, 11, 17, 15, 14, 30, tzinfo=timezone.utc)
    fetched = (clock - timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    peer = bobreport.enrich_peer_keep_last_good_xai_weekly(
        _peer_good(fetched),
        error="provider-http-503",
        now=clock,
        machine_id="flamingo",
    )
    meter = peer["xai_weekly"]
    assert meter["remaining_pct"] == 97
    assert meter["period_end"] == "2026-11-22T19:28:11Z"
    assert meter["fresh"] is True
    assert meter["error"] == "provider-http-503"
    assert bobreport.XAI_BILLING_SOURCE in str(
        meter.get("error_source") or meter.get("source") or ""
    )


def test_fr8049_repeated_503_past_window_is_stale_keeps_pct():
    clock = datetime(2026, 11, 17, 15, 14, 30, tzinfo=timezone.utc)
    fetched = (clock - timedelta(seconds=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    peer = bobreport.enrich_peer_keep_last_good_xai_weekly(
        _peer_good(fetched),
        error="provider-http-503",
        now=clock,
        machine_id="flamingo",
    )
    meter = peer["xai_weekly"]
    assert meter["remaining_pct"] == 97
    assert meter["fresh"] is False
    assert meter["error"] == "provider-http-503"
    src = str(meter.get("error_source") or "")
    assert "cli-chat-proxy" in src or bobreport.XAI_BILLING_SOURCE in src


def test_fr8049_acquisition_error_carries_billing_source(monkeypatch, tmp_path):
    import urllib.error

    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"https://auth.x.ai::test": {"key": "FAKE_SESSION_KEY_FOR_TESTS_ONLY"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))

    def boom(req, timeout=0):  # noqa: ARG001
        raise urllib.error.HTTPError(
            req.get_full_url(), 503, "unavailable", hdrs=None, fp=None
        )

    with mock.patch("urllib.request.urlopen", boom):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 17, 15, 14, tzinfo=timezone.utc)
        )
    assert reading is None
    acq = bobreport._last_xai_acquisition
    assert acq.get("error") == "provider-http-503"
    assert bobreport.XAI_BILLING_SOURCE in str(acq.get("error_source") or "")
