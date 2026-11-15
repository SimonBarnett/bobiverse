"""FR #7471: ear pool checks every 60s even after errors; auth mtime forces recheck."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport


def setup_function() -> None:
    bobreport.reset_pool_fetch_state()
    bobreport.reset_auth_watch_state()


def test_fr7471_errors_keep_60s_cadence_for_30_minutes():
    now = 1_700_000_000.0
    attempts = []
    for i in range(30):
        t = now + i * 60.0
        assert bobreport.pool_fetch_due("xai", t) is True, f"tick {i}"
        bobreport.mark_pool_fetch(
            "xai",
            t,
            ok=False,
            error="grok-login-expired" if i % 2 == 0 else "provider-http-500",
            rate_limited=(i % 3 == 0),  # even "rate limited" must not stretch
        )
        attempts.append(t)
        assert bobreport.pool_fetch_due("xai", t + 59.0) is False
    gaps = [attempts[i] - attempts[i - 1] for i in range(1, len(attempts))]
    assert all(abs(g - 60.0) < 0.01 for g in gaps)


def test_fr7471_429_does_not_backoff_past_60s():
    now = 1_700_000_000.0
    bobreport.mark_pool_fetch(
        "xai", now, ok=False, error="provider-http-429", rate_limited=True
    )
    assert bobreport.pool_fetch_due("xai", now + 1.0) is False
    assert bobreport.pool_fetch_due("xai", now + 60.0) is True


def test_fr7471_auth_mtime_change_forces_immediate_recheck(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"https://api.x.ai::cli":{"access_token":"FAKE_access_1","refresh_token":"FAKE_refresh","expires_at":"2099-01-01T00:00:00Z"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    bobreport.reset_auth_watch_state()
    assert bobreport.auth_watch_force_fetch(auth) is True  # first sighting
    assert bobreport.auth_watch_force_fetch(auth) is False  # unchanged
    # mutate mtime/content
    import time
    time.sleep(0.05)
    auth.write_text(
        '{"https://api.x.ai::cli":{"access_token":"FAKE_access_2","refresh_token":"FAKE_refresh","expires_at":"2099-01-01T00:00:00Z"}}',
        encoding="utf-8",
    )
    assert bobreport.auth_watch_force_fetch(auth) is True


def test_fr7471_publish_runs_check_within_5s_on_auth_change(tmp_path, monkeypatch):
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
            "pcent": {"grok-chat": 40},
        },
    )
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    bobreport.reset_auth_watch_state()
    bobreport.reset_pool_fetch_state()

    calls = {"n": 0}

    def fake_xai(*, now=None):
        calls["n"] += 1
        bobreport._last_xai_acquisition = {
            "identity": "live-billing",
            "read": True,
            "live": True,
            "error": None,
            "selected": True,
            "account": None,
            "auth_path": str(auth),
        }
        clock = now or datetime.now(timezone.utc)
        iso = clock.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(clock, "strftime") else bobreport.iso_utc_from_epoch(float(clock))
        return {
            "remaining_pct": 55,
            "fetched_at": iso,
            "fresh": True,
            "period_end": "2099-01-01T00:00:00Z",
            "weekly_known": True,
        }

    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", fake_xai)
    monkeypatch.setattr(
        bobreport,
        "post_report_json",
        lambda payload, url="": (
            bobreport._last_post_outcome.update({"http_status": 204, "ack": True, "error": None}) or 204
        ),
    )

    t0 = 1_700_000_000.0
    # First publish primes watch + fetches
    bobreport.publish_local_peer_fuel(home, mid, force=False, now=t0)
    assert calls["n"] == 1
    # Within 60s window: normally skipped
    bobreport.publish_local_peer_fuel(home, mid, force=False, now=t0 + 10.0)
    assert calls["n"] == 1
    # Auth change forces immediate re-check
    auth.write_text('{"x":1}', encoding="utf-8")
    bobreport.publish_local_peer_fuel(home, mid, force=False, now=t0 + 12.0)
    assert calls["n"] == 2


def test_fr7471_auth_watch_uses_xai_weekly_path_under_localsystem(
    tmp_path: Path, monkeypatch
):
    """SYSTEM ear must watch interactive auth.json, not systemprofile home."""
    interactive = tmp_path / "Users" / "Operator" / ".grok" / "auth.json"
    interactive.parent.mkdir(parents=True)
    interactive.write_text("{}", encoding="utf-8")
    sys_home = tmp_path / "systemprofile"
    sys_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(sys_home))
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_HOME", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(
        bobreport, "_interactive_grok_user_home", lambda: interactive.parents[1]
    )
    bobreport.reset_auth_watch_state()
    path, ident = bobreport.xai_weekly_auth_path()
    assert path == interactive
    assert ident == "interactive-auth"
    # resolve_grok_auth_path alone would watch systemprofile — wrong for SYSTEM ear.
    resolved = bobreport.resolve_grok_auth_path()
    assert resolved is not None
    assert resolved != interactive
    assert bobreport.auth_watch_force_fetch(path) is True
    assert bobreport.auth_watch_force_fetch(path) is False
    import time

    time.sleep(0.05)
    interactive.write_text('{"y":1}', encoding="utf-8")
    assert bobreport.auth_watch_force_fetch(path) is True
