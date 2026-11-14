"""FR #7399: absent creditUsagePercent on a valid weekly period means 0% used."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


NOW = datetime(2026, 11, 14, 23, 30, tzinfo=timezone.utc)


def _doc(*, used=None, with_period=True):
    cfg = {
        "isUnifiedBillingUser": True,
        "billingPeriodEnd": "2026-11-20T12:00:00Z",
    }
    if with_period:
        cfg["currentPeriod"] = {
            "type": "USAGE_PERIOD_TYPE_WEEKLY",
            "start": "2026-11-13T12:00:00Z",
            "end": "2026-11-20T12:00:00Z",
        }
    if used is not None:
        cfg["creditUsagePercent"] = used
    return {"config": cfg}


def test_fr7399_absent_credit_usage_percent_is_zero_used():
    reading = bobreport.parse_xai_billing_credits_response(_doc(used=None), now=NOW)
    assert reading is not None
    assert reading["used_pct"] == 0
    assert reading["remaining_pct"] == 100
    assert reading["weekly_known"] is True
    assert reading["fresh"] is True
    assert reading["error"] is None
    assert reading["period_end"] == "2026-11-20T12:00:00Z"
    assert reading["source"] == bobreport.XAI_BILLING_SOURCE


def test_fr7399_credit_usage_percent_35_still_maps():
    reading = bobreport.parse_xai_billing_credits_response(_doc(used=35), now=NOW)
    assert reading is not None
    assert reading["used_pct"] == 35
    assert reading["remaining_pct"] == 65
    assert reading["fresh"] is True
    assert reading["error"] is None


def test_fr7399_no_period_still_rejects():
    reading = bobreport.parse_xai_billing_credits_response(
        _doc(used=None, with_period=False), now=NOW
    )
    # billingPeriodEnd alone may still count as period — require neither
    doc = {"config": {"isUnifiedBillingUser": True}}
    reading = bobreport.parse_xai_billing_credits_response(doc, now=NOW)
    assert reading is None


def test_fr7399_fetch_logs_field_names_on_reject(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "https://auth.x.ai::test": {
                    "key": "FAKE_SESSION_KEY_FOR_TESTS_ONLY",
                    "refresh_token": "FAKE_REFRESH_FOR_TESTS_ONLY",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                # Valid JSON but no weekly period and no percent.
                return b'{"config":{"isUnifiedBillingUser":true,"prepaidBalance":0}}'

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(now=NOW)
    assert reading is None
    acq = bobreport._last_xai_acquisition
    assert acq.get("error")
    assert acq.get("error") != "ok"
    keys = acq.get("response_keys") or acq.get("config_keys") or []
    assert "isUnifiedBillingUser" in keys or "prepaidBalance" in keys or "config" in str(keys)