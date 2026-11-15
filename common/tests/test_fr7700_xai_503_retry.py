"""FR #7700: provider 503 is retried immediately and the next poll is due in 15s."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def setup_function() -> None:
    bobreport.reset_pool_fetch_state()


def test_fr7700_503_is_due_again_in_15s_not_60s():
    now = 1_700_000_000.0
    bobreport.mark_pool_fetch("xai", now, ok=False, error="provider-http-503")
    assert bobreport.pool_fetch_due("xai", now + 14.0) is False
    assert bobreport.pool_fetch_due("xai", now + 15.0) is True
    bobreport.mark_pool_fetch("xai", now, ok=False, error="provider-http-429", rate_limited=True)
    assert bobreport.pool_fetch_due("xai", now + 15.0) is False
    assert bobreport.pool_fetch_due("xai", now + 60.0) is True


def test_fr7700_billing_retries_503_once_then_reads(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"https://auth.x.ai::test": {"key": "FAKE_SESSION_KEY_FOR_TESTS_ONLY"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    calls = {"n": 0}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            body = {
                "config": {
                    "currentPeriod": {
                        "type": "USAGE_PERIOD_TYPE_WEEKLY",
                        "start": "2026-11-08T12:00:00Z",
                        "end": "2026-11-15T12:00:00Z",
                    },
                    "creditUsagePercent": 28.0,
                }
            }
            return json.dumps(body).encode("utf-8")

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            import urllib.error

            raise urllib.error.HTTPError(req.get_full_url(), 503, "unavailable", hdrs=None, fp=None)
        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 15, 22, 24, tzinfo=timezone.utc)
        )
    assert calls["n"] == 2
    assert reading is not None
    assert reading.get("remaining_pct") == 72
    assert bobreport._last_xai_acquisition.get("error") in (None, "")
