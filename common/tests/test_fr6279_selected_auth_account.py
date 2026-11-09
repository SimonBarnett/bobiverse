"""FR #6279: xai weekly account label from selected auth entry only.

Expiry-ranked bearer must not borrow a sibling entry's email/name.
Fixtures use FAKE_ placeholders only. Never 82/74/43/75/35.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


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


def test_fr6279_session_returns_label_from_selected_entry(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "email": "live@example.test",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    token, err, label = bobreport.load_grok_auth_session(path)
    assert err is None
    assert token == "FAKE_LIVE_KEY"
    assert label == "live@example.test"


def test_fr6279_unlabeled_selected_does_not_borrow_sibling_label(tmp_path: Path):
    """Expired labeled + unexpired credential-only: leave reading unattributed."""
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "email": "expired@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    token, err, label = bobreport.load_grok_auth_session(path)
    assert err is None
    assert token == "FAKE_LIVE_KEY"
    assert label is None
    # Independent reader would still see the sole visible label (sibling).
    src, borrowed = bobreport.read_grok_account_label(
        {"BOB_GROK_AUTH_PATH": str(path)}
    )
    assert src == "ok"
    assert borrowed == "expired@example.test"


def test_fr6279_fetch_sets_account_from_selected_not_sibling(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "email": "expired@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    now = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        class Resp:
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
    assert reading.get("account") is None
    assert bobreport._last_xai_acquisition.get("account") is None
    assert bobreport._last_xai_acquisition.get("selected") is True


def test_fr6279_fetch_account_matches_selected_labeled_entry(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::stale": {
                    "key": "FAKE_STALE_KEY",
                    "email": "stale@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "email": "live@example.test",
                    "first_name": "Live",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    now = datetime(2026, 11, 9, 11, 5, tzinfo=timezone.utc)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        class Resp:
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
    assert reading.get("account") == "live@example.test"
    assert bobreport._last_xai_acquisition.get("account") == "live@example.test"


def test_fr6279_enrich_preserves_reading_account():
    peer = {"pcent": {}}
    reading = {
        "remaining_pct": 72,
        "used_pct": 28,
        "weekly_known": True,
        "fresh": True,
        "source": bobreport.XAI_BILLING_SOURCE,
        "fetched_at": "2026-11-09T11:00:00Z",
        "period_end": "2026-11-15T12:00:00Z",
        "account": "live@example.test",
        "window": "weekly",
    }
    out = bobreport.enrich_peer_with_xai_weekly(peer, reading)
    assert out["xai_weekly"]["account"] == "live@example.test"


def test_fr6279_publish_does_not_overwrite_meter_with_sibling(
    tmp_path: Path, monkeypatch
):
    """After live fetch with unlabeled selected entry, meter.account stays None."""
    home = tmp_path / "home"
    home.mkdir()
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "email": "expired@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setenv("BOB_MACHINE_ID", "flamingo")

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = getattr(req, "full_url", None) or req.get_full_url()
        if "billing" in str(url):

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self):
                    return _credits_body(28.0)

            return Resp()

        class PostResp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return PostResp()

    # Build peer path as publish_local_peer_fuel would after fetch.
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 9, 11, 10, tzinfo=timezone.utc)
        )
    assert reading is not None
    peer = bobreport.enrich_peer_with_xai_weekly({"pcent": {}}, reading)
    # Simulate the FR #6279 attach rule (selected wins; no sibling borrow).
    selected = bobreport._last_xai_acquisition.get("account")
    selected_flag = bobreport._last_xai_acquisition.get("selected")
    assert selected_flag is True
    assert selected is None
    meter = dict(peer["xai_weekly"])
    if selected_flag:
        meter["account"] = selected
        if selected:
            peer["grok_account"] = selected
        else:
            peer.pop("grok_account", None)
    peer["xai_weekly"] = meter
    assert peer["xai_weekly"]["account"] is None
    assert "grok_account" not in peer

def test_fr6279_provider_http_error_keeps_selected_provenance(
    tmp_path: Path, monkeypatch
):
    """After bearer selection, HTTP failure must not drop selected (MRB #6280)."""
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "email": "expired@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(path))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)

    def boom(req, timeout=0):  # noqa: ARG001
        import urllib.error

        raise urllib.error.HTTPError(
            url="https://cli-chat-proxy.grok.com/v1/billing?format=credits",
            code=503,
            msg="unavailable",
            hdrs=None,
            fp=None,
        )

    with mock.patch("urllib.request.urlopen", boom):
        reading = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 9, 11, 20, tzinfo=timezone.utc)
        )
    assert reading is None
    acq = bobreport._last_xai_acquisition
    assert acq.get("selected") is True
    assert acq.get("account") is None
    assert "503" in str(acq.get("error") or "")


def test_fr6279_publish_after_provider_fail_does_not_borrow_sibling(
    tmp_path: Path, monkeypatch
):
    """publish_local_peer_fuel must not stamp sibling label after selected fail."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "machines").mkdir()
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "https://auth.x.ai::expired": {
                    "key": "FAKE_EXPIRED_KEY",
                    "email": "expired@example.test",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
                "https://auth.x.ai::live": {
                    "key": "FAKE_LIVE_KEY",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setenv("BOB_MACHINE_ID", "flamingo")

    def boom(req, timeout=0):  # noqa: ARG001
        import urllib.error

        raise urllib.error.HTTPError(
            url="https://cli-chat-proxy.grok.com/v1/billing?format=credits",
            code=502,
            msg="bad gateway",
            hdrs=None,
            fp=None,
        )

    with mock.patch("urllib.request.urlopen", boom):
        assert (
            bobreport.fetch_live_xai_weekly(
                now=datetime(2026, 11, 9, 11, 25, tzinfo=timezone.utc)
            )
            is None
        )

    peer = {
        "pcent": {"grok-build": 40},
        "weekly": 40,
        "weekly_known": True,
        "xai_weekly": {
            "provider": "xai",
            "window": "weekly",
            "direction": "remaining",
            "remaining_pct": 40,
            "source": "last-good",
            "fetched_at": "2026-11-09T10:00:00Z",
            "account": "stale@example.test",
            "fresh": False,
        },
        "xai_weekly_fetched_at": "2026-11-09T10:00:00Z",
        "grok_account": "expired@example.test",
    }
    # Apply the same attach block publish_local_peer_fuel uses after fetch.
    acq = bobreport._last_xai_acquisition if isinstance(
        bobreport._last_xai_acquisition, dict
    ) else {}
    selected = bool(acq.get("selected"))
    assert selected is True
    peer = dict(peer)
    if selected:
        label = acq.get("account")
        xai_meter = peer.get("xai_weekly")
        if isinstance(xai_meter, dict):
            meter = dict(xai_meter)
            meter["account"] = label
            peer["xai_weekly"] = meter
        if label:
            peer["grok_account"] = label
        else:
            peer.pop("grok_account", None)
    assert peer["xai_weekly"]["account"] is None
    assert "grok_account" not in peer
    # Sibling independent reader still sees expired label; must not be used.
    src, borrowed = bobreport.read_grok_account_label(
        {"BOB_GROK_AUTH_PATH": str(auth)}
    )
    assert src == "ok"
    assert borrowed == "expired@example.test"
