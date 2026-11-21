"""FR #8773: bare TypeError on xAI weekly fetch must not be the only stale clue."""
from __future__ import annotations

import tempfile
from pathlib import Path

import bobreport as br
import bobstat
import ear_pool_stale_report as eps


def test_format_xai_read_failure_includes_class_and_message():
    err = br.format_xai_read_failure(TypeError("cannot unpack non-iterable NoneType object"))
    assert err.startswith("read-failed:TypeError:")
    assert "unpack" in err
    assert "Bearer" not in err


def test_format_xai_read_failure_redacts_tokenish():
    err = br.format_xai_read_failure(
        TypeError("Authorization Bearer FAKESECRET_e4f5g6h7i8j9k0l1m2n3")
    )
    assert "read-failed:TypeError:" in err
    assert "ghp_" not in err.lower()


def test_publish_typeerror_persists_detailed_error_and_peer(monkeypatch):
    def boom(**_k):
        raise TypeError("cannot unpack non-iterable NoneType object")

    monkeypatch.setattr(br, "fetch_live_xai_weekly", boom)
    monkeypatch.setattr(br, "post_report_json", lambda *_a, **_k: 204)
    monkeypatch.setattr(
        br,
        "resolve_fuel_report_target",
        lambda *_a, **_k: {
            "ok": True,
            "url": "http://127.0.0.1:9/bob/v1/report",
            "host": "127.0.0.1",
            "path": "/bob/v1/report",
            "source": "test",
        },
    )
    br.reset_pool_fetch_state()
    captured: dict = {}

    def wrap(**kw):
        captured.update(kw)
        return {"action": "skip"}

    monkeypatch.setattr(eps, "evaluate_and_report_xai_pool_stale", wrap)

    home = Path(tempfile.mkdtemp())
    bobstat.write_peer(
        home,
        {"id": "flamingo", "machine": "flamingo", "lastSeen": "2026-11-21T00:00:00Z"},
    )
    br._pool_fetch_state["xai"] = {"last_attempt": 0}

    status = br.publish_local_peer_fuel(home, "flamingo", force=True)
    assert status == 204

    detail = br._last_fuel_publish_diag.get("xai_weekly_error")
    assert isinstance(detail, str)
    assert detail.startswith("read-failed:TypeError:")
    assert detail != "TypeError"

    pool_err = (br._pool_fetch_state.get("xai") or {}).get("error")
    assert pool_err == detail

    assert captured.get("last_error") == detail
    assert captured.get("last_error") != "TypeError"

    peer = bobstat.read_peer(home, "flamingo")
    assert isinstance(peer, dict)
    meter = peer.get("xai_weekly")
    assert isinstance(meter, dict)
    assert meter.get("error") == detail


def test_enrich_used_pct_bad_type_does_not_raise():
    peer = {"id": "flamingo", "machine": "flamingo"}
    reading = {
        "weekly_known": True,
        "remaining_pct": 40,
        "used_pct": {"nested": True},  # would raise bare TypeError on int()
        "fetched_at": "2026-11-21T20:00:00Z",
        "source": "cli-chat-proxy:/v1/billing?format=credits",
        "fresh": True,
        "period_end": "2026-11-28T00:00:00Z",
    }
    out = br.enrich_peer_with_xai_weekly(peer, reading)
    assert out.get("weekly") == 40
    assert out.get("xai_weekly_used_pct") is None
    assert isinstance(out.get("xai_weekly"), dict)


def test_ensure_auth_typeerror_becomes_acquisition_error(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))

    def boom(*_a, **_k):
        raise TypeError("bad auth slot")

    monkeypatch.setattr(br, "ensure_grok_auth_access_token", boom)
    reading = br.fetch_live_xai_weekly()
    assert reading is None
    acq = br._last_xai_acquisition
    assert isinstance(acq, dict)
    err = str(acq.get("error") or "")
    assert err.startswith("read-failed:TypeError:")
    assert "bad auth slot" in err
