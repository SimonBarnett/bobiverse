"""FR #7503: ear reports a stale xAI pool (2 min without live fetch) as an exception.

Acceptance:
- stale for 2 minutes raises exactly one report
- staying stale does not create duplicates (comment / dedupe only)
- recovery adds a comment (does not auto-close)
- report body contains no secret values
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ear_pool_stale_report as epsr  # noqa: E402


def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_EAR_POOL_STALE_DIR", str(tmp_path / "stale"))
    monkeypatch.setenv("BOB_CRASH_REPORT", "1")
    epsr.reset_state()


def test_fr7503_stale_two_minutes_raises_exactly_one_report(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    posts: list[tuple[str, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 9001, "intake_id": "in_test"}

    t0 = 1_700_000_000.0
    fetched = epsr.iso_utc_from_epoch(t0)
    # Fresh reading: no report
    r0 = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="flamingo",
        fetched_at=fetched,
        last_error=None,
        now=t0 + 20.0,
        filer_post=fake_post,
        comment_min_s=0,
        version="1.2.3",
    )
    assert r0.get("action") == "fresh"
    assert posts == []

    # Age > 120s: first report
    r1 = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="flamingo",
        fetched_at=fetched,
        last_error="provider-http-500",
        now=t0 + 121.0,
        filer_post=fake_post,
        comment_min_s=0,
        version="1.2.3",
    )
    assert r1.get("action") == "filed"
    assert len(posts) == 1
    title, body = posts[0]
    assert "xai_weekly" in title.lower() or "xai" in title.lower()
    assert "flamingo" in body or "machine=" in body
    assert "xai_weekly" in body
    assert "provider-http-500" in body
    assert "1.2.3" in body
    assert fetched in body
    assert "fail-sig:" in body or "crash-sig:" in body or "dedupe:" in body


def test_fr7503_staying_stale_does_not_duplicate(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    posts: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 42}

    def fake_comment(repo, number, body):
        comments.append((int(number), body))
        return True

    t0 = 1_700_000_000.0
    fetched = epsr.iso_utc_from_epoch(t0)
    a = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="marchhare",
        fetched_at=fetched,
        last_error="grok-login-expired",
        now=t0 + 130.0,
        filer_post=fake_post,
        comment_fn=fake_comment,
        comment_min_s=0,
        version="9.9.9",
    )
    assert a.get("action") == "filed"
    assert len(posts) == 1

    b = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="marchhare",
        fetched_at=fetched,
        last_error="grok-login-expired",
        now=t0 + 200.0,
        filer_post=fake_post,
        comment_fn=fake_comment,
        comment_min_s=0,
        version="9.9.9",
    )
    assert b.get("action") in ("commented", "deduped")
    assert len(posts) == 1  # no second create
    assert len(comments) >= 1
    assert comments[0][0] == 42
    assert "still stale" in comments[0][1].lower() or "stale" in comments[0][1].lower()


def test_fr7503_recovery_adds_comment_no_autoclose(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    posts: list = []
    comments: list[tuple[int, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 77}

    def fake_comment(repo, number, body):
        comments.append((int(number), body))
        return True

    logs: list[str] = []

    t0 = 1_700_000_000.0
    fetched_old = epsr.iso_utc_from_epoch(t0)
    epsr.evaluate_and_report_xai_pool_stale(
        machine_id="redqueen",
        fetched_at=fetched_old,
        last_error="provider-http-429",
        now=t0 + 150.0,
        filer_post=fake_post,
        comment_fn=fake_comment,
        comment_min_s=0,
        log_fn=lambda m: logs.append(m),
        version="2.0.0",
    )
    assert len(posts) == 1

    fresh_at = epsr.iso_utc_from_epoch(t0 + 160.0)
    r = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="redqueen",
        fetched_at=fresh_at,
        last_error=None,
        now=t0 + 170.0,
        filer_post=fake_post,
        comment_fn=fake_comment,
        comment_min_s=0,
        log_fn=lambda m: logs.append(m),
        version="2.0.0",
    )
    assert r.get("action") == "recovered"
    assert len(posts) == 1  # no new issue
    assert any("recover" in c[1].lower() for c in comments)
    # Must not claim the issue was closed; "do not auto-close" guidance is fine.
    assert not any(
        ("closed" in c[1].lower() or "closing" in c[1].lower())
        and "do not" not in c[1].lower()
        for c in comments
    )
    assert any("recover" in m.lower() for m in logs)


def test_fr7503_report_body_has_no_secrets(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    posts: list[tuple[str, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 1}

    t0 = 1_700_000_000.0
    secret = "xai-sk-" + ("A" * 40)
    tokenish = "Bearer " + ("B" * 32)
    fetched = epsr.iso_utc_from_epoch(t0)
    epsr.evaluate_and_report_xai_pool_stale(
        machine_id="flamingo",
        fetched_at=fetched,
        last_error=f"auth failed token={secret} header={tokenish}",
        now=t0 + 200.0,
        filer_post=fake_post,
        comment_min_s=0,
        version="1.0.0",
    )
    assert len(posts) == 1
    _title, body = posts[0]
    assert secret not in body
    assert ("B" * 32) not in body
    assert "Bearer " + ("B" * 32) not in body
    # Redaction leaves a marker or strips the secret
    assert "password" not in body.lower() or "redact" in body.lower() or "***" in body or "[redacted]" in body.lower() or "token=" not in body or "FAKE_" in body or "…" in body or "..." in body or "REDACT" in body.upper() or "*" in body


def test_fr7503_never_succeeded_becomes_stale_after_two_minutes(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    posts: list = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "number": 5}

    t0 = 1_700_000_000.0
    # First sighting with no fetched_at: start tracking, not yet stale
    r0 = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="ionos",
        fetched_at=None,
        last_error="auth-file-unreadable",
        now=t0,
        filer_post=fake_post,
        comment_min_s=0,
        version="1.0.0",
    )
    assert r0.get("action") in ("tracking", "fresh", "not-stale")
    assert posts == []

    r1 = epsr.evaluate_and_report_xai_pool_stale(
        machine_id="ionos",
        fetched_at=None,
        last_error="auth-file-unreadable",
        now=t0 + 121.0,
        filer_post=fake_post,
        comment_min_s=0,
        version="1.0.0",
    )
    assert r1.get("action") == "filed"
    assert len(posts) == 1


def test_fr7503_publish_local_peer_fuel_calls_stale_reporter(tmp_path, monkeypatch):
    """Wire: publish_local_peer_fuel invokes the stale reporter for the ear's xAI meter."""
    import bobreport
    import bobstat

    bobreport.reset_pool_fetch_state()
    calls: list[dict] = []

    def capture(**kwargs):
        calls.append(dict(kwargs))
        return {"action": "fresh", "ok": True}

    monkeypatch.setattr(epsr, "evaluate_and_report_xai_pool_stale", capture)
    # Ensure bobreport imports the module name used in the hook
    import importlib

    if "ear_pool_stale_report" in sys.modules:
        monkeypatch.setattr(
            sys.modules["ear_pool_stale_report"],
            "evaluate_and_report_xai_pool_stale",
            capture,
        )

    home = tmp_path / "home"
    home.mkdir()
    mid = "flamingo"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 40,
            "weekly_known": True,
            "xai_weekly": {
                "remaining_pct": 40,
                "fetched_at": "2026-11-15T12:00:00Z",
                "fresh": True,
            },
            "xai_weekly_fetched_at": "2026-11-15T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        bobreport,
        "fetch_live_xai_weekly",
        lambda now=None: {
            "remaining_pct": 40,
            "fetched_at": "2026-11-15T12:00:00Z",
            "fresh": True,
            "period_end": "2099-01-01T00:00:00Z",
            "weekly_known": True,
        },
    )
    bobreport._last_xai_acquisition = {
        "identity": "live-billing",
        "read": True,
        "live": True,
        "error": None,
        "selected": True,
        "account": None,
        "auth_path": None,
    }
    monkeypatch.setattr(
        bobreport,
        "post_report_json",
        lambda payload, url="": (
            bobreport._last_post_outcome.update(
                {"http_status": 204, "ack": True, "error": None}
            )
            or 204
        ),
    )
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None: {
            "ok": True,
            "url": "https://example.test/bob/v1/report",
            "host": "example.test",
            "path": "/bob/v1/report",
            "source": "test",
        },
    )

    bobreport.publish_local_peer_fuel(home, mid, force=True, now=1_700_000_000.0)
    assert calls, "publish_local_peer_fuel must call evaluate_and_report_xai_pool_stale"
    assert calls[0].get("machine_id") == mid or calls[0].get("machine_id") == "flamingo"
    assert calls[0].get("pool", "xai_weekly") == "xai_weekly"
