"""FR #6439: stall webhook callbacks (reuse FR #6391 wake URL) + close event=close."""
from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from repo_layout import REPO

_MON = REPO / "jeeves" / "tools" / "monitor"
if str(_MON) not in sys.path:
    sys.path.insert(0, str(_MON))

import stall_callbacks as sc  # noqa: E402
import stall_detectors as sd  # noqa: E402
import ticket_closure as tc  # noqa: E402
from test_fr6064_ticket_closure_dedupe import STATE, _fx, _homes  # noqa: E402


def _wake_env(monkeypatch, url: str = "https://example.test/wake", secret: str = "sekrit"):
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", url)
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", secret)


def test_fr6439_close_payload_event_close(tmp_path: Path, monkeypatch):
    """event=close on ticket-closure wake; text/repo/number stay (backward compat)."""
    chair, digest = _homes(tmp_path)
    fx = _fx(
        tmp_path / "events.json",
        [
            {
                "kind": "issue",
                "event": "closed",
                "repo": "SimonBarnett/bobiverse",
                "number": 81,
                "closed_at": "2026-11-03T15:00:00Z",
                "delivery_id": "del-81",
                "title": "x",
            }
        ],
    )
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    _wake_env(monkeypatch)
    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append({"url": url, "body": dict(body), "headers": dict(headers)})
        return {"ok": True, "status": 200}

    monkeypatch.setattr(tc, "_WAKE_HTTP_POST", post_wake)
    payload, code = tc.check(
        Namespace(
            chair_home=str(chair),
            digest_home=str(digest),
            dry_run=False,
            help_exit0=False,
        )
    )
    assert code == 1
    assert payload.get("woke") == 1
    assert posts
    body = posts[0]["body"]
    assert body.get("event") == "close"
    assert body.get("repo") == "SimonBarnett/bobiverse"
    assert body.get("number") == 81
    assert "text" in body and "brief" in body
    assert "sekrit" not in json.dumps(body)


def test_fr6439_payload_has_no_secrets():
    payload = sc.build_callback_payload(
        event=sc.EVENT_GIVEUP,
        repo="SimonBarnett/bobiverse",
        number=6439,
        seat="redqueen-1",
        machine="redqueen",
        reason="blocked",
        since=1.0,
    )
    sc.assert_no_secrets(payload)
    # Redact reason that looks secret-shaped.
    dirty = sc.build_callback_payload(
        event=sc.EVENT_GIVEUP,
        reason="token=abc123password=x",
    )
    assert "***" in dirty["reason"]
    sc.assert_no_secrets(dirty)


def test_fr6439_each_event_fires_once_and_debounces(tmp_path: Path, monkeypatch):
    _wake_env(monkeypatch)
    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append(dict(body))
        return {"ok": True, "status": 200}

    monkeypatch.setattr(sc, "_WAKE_HTTP_POST", post_wake)
    now = 1_700_000_000.0
    cases = [
        (sc.EVENT_IDLE_WITH_WORK, "queue"),
        (sc.EVENT_OFFER_TIMEOUT, "SimonBarnett/bobiverse#1:offer"),
        (sc.EVENT_GIVEUP, "SimonBarnett/bobiverse#2:seat"),
        (sc.EVENT_SELF_REVIEW_DEADLOCK, "deadlock-key"),
        (sc.EVENT_SEAT_DOWN, "redqueen"),
        (sc.EVENT_RESYNC_FAILED, "streak-3"),
        (sc.EVENT_RATE_LIMITED, "streak-4"),
        (sc.EVENT_CHAIR_DEGRADED, "report"),
    ]
    for event, subject in cases:
        payload = sc.build_callback_payload(
            event=event,
            repo="SimonBarnett/bobiverse",
            number=1,
            seat="redqueen-1",
            machine="redqueen",
            since=now,
            reason=event,
        )
        r1 = sc.enqueue_callback(tmp_path, payload, subject=subject, now=now)
        assert r1.get("posted") is True, event
        r2 = sc.enqueue_callback(tmp_path, payload, subject=subject, now=now + 60)
        assert r2.get("skipped") == "debounced", event
        # After debounce window, fires again.
        r3 = sc.enqueue_callback(
            tmp_path, payload, subject=subject, now=now + sc.DEBOUNCE_S + 1
        )
        assert r3.get("posted") is True, event
    fired = {p.get("event") for p in posts}
    for event, _ in cases:
        assert event in fired


def test_fr6439_failed_post_retries_from_pending(tmp_path: Path, monkeypatch):
    _wake_env(monkeypatch)
    calls = {"n": 0}

    def post_wake(url: str, body: dict, headers: dict):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("502")
        return {"ok": True, "status": 200}

    monkeypatch.setattr(sc, "_WAKE_HTTP_POST", post_wake)
    now = 1_700_000_000.0
    payload = sc.build_callback_payload(
        event=sc.EVENT_GIVEUP,
        repo="SimonBarnett/bobiverse",
        number=9,
        reason="giveup",
        since=now,
    )
    r1 = sc.enqueue_callback(tmp_path, payload, subject="r#9", now=now)
    assert r1.get("pending") is True
    state = sc.load_state(tmp_path)
    assert state.get("pending")
    raw = sc.state_path(tmp_path).read_text(encoding="utf-8")
    assert "sekrit" not in raw
    # Immediate drain skipped (backoff).
    d1 = sc.drain_pending(tmp_path, now=now + 1)
    assert d1["drained"] == 0
    d2 = sc.drain_pending(tmp_path, now=now + sc.WAKE_BACKOFF_S + 1)
    assert d2["drained"] == 1
    assert sc.load_state(tmp_path).get("pending") in ({}, None) or not sc.load_state(
        tmp_path
    ).get("pending")


def test_fr6439_event_disable_env(tmp_path: Path, monkeypatch):
    _wake_env(monkeypatch)
    monkeypatch.setenv("JEEVES_STALL_CALLBACK_GIVEUP", "0")
    posts: list = []
    monkeypatch.setattr(
        sc,
        "_WAKE_HTTP_POST",
        lambda *a, **k: posts.append(1) or {"ok": True},
    )
    r = sc.enqueue_callback(
        tmp_path,
        sc.build_callback_payload(event=sc.EVENT_GIVEUP, repo="a/b", number=1),
        subject="a/b#1",
        now=1.0,
    )
    assert r.get("skipped") == "event_disabled"
    assert posts == []


def test_fr6439_no_wake_url_noop(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_WAKE_URL", raising=False)
    monkeypatch.delenv("JEEVES_BOB_WAKE_URL", raising=False)
    monkeypatch.setattr(
        sc,
        "_WAKE_HTTP_POST",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not post")),
    )
    r = sc.enqueue_callback(
        tmp_path,
        sc.build_callback_payload(event=sc.EVENT_HEARTBEAT),
        subject="heartbeat",
        now=1.0,
    )
    assert r.get("skipped") == "no_wake_url"


def test_fr6439_finding_map_and_rate_limited():
    assert (
        sc.finding_to_event({"id": "self-review-deadlock", "key": "x"})
        == sc.EVENT_SELF_REVIEW_DEADLOCK
    )
    assert sc.finding_to_event({"id": "all-gave-up", "key": "x"}) == sc.EVENT_GIVEUP
    assert sc.finding_to_event({"id": "ack-stale", "key": "x"}) == sc.EVENT_OFFER_TIMEOUT
    assert sc.finding_to_event({"id": "bored-latency", "key": "x"}) == sc.EVENT_SEAT_DOWN
    assert (
        sc.finding_to_event({"id": "stale-digest", "key": "x"})
        == sc.EVENT_CHAIR_DEGRADED
    )
    assert (
        sc.finding_to_event({"id": "idle-with-work", "key": "x"})
        == sc.EVENT_IDLE_WITH_WORK
    )
    assert (
        sc.finding_to_event(
            {"id": "resync-fail", "key": "s", "evidence": {"status": 500}}
        )
        == sc.EVENT_RESYNC_FAILED
    )
    assert (
        sc.finding_to_event(
            {"id": "resync-fail", "key": "s", "evidence": {"status": 429}}
        )
        == sc.EVENT_RATE_LIMITED
    )


def test_fr6439_detect_idle_with_work():
    now = 1_700_000_000.0
    old_ts = "2023-11-10T12:00:00+00:00"  # well before now
    snap = {
        "now": now,
        "idle": {"redqueen-1"},
        "unaccepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#6439",
                "url": "https://github.com/SimonBarnett/bobiverse/issues/6439",
                "ts": old_ts,
            }
        ],
    }
    found = sd.detect_idle_with_work(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.IDLE_WITH_WORK_ID
    # Fresh enqueue: silent.
    snap2 = {
        "now": now,
        "idle": {"redqueen-1"},
        "unaccepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#1",
                "url": "https://github.com/SimonBarnett/bobiverse/issues/1",
                "ts": "2023-11-14T12:00:00+00:00",  # still old relative? use near now
            }
        ],
    }
    # Use ts close to now via iso from epoch
    from datetime import datetime, timezone

    recent = datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat()
    snap2["unaccepted"][0]["ts"] = recent
    assert sd.detect_idle_with_work(snap2) == []
    # Live offer suppresses.
    live_ts = datetime.fromtimestamp(now - 700, tz=timezone.utc).isoformat()
    offer_ts = datetime.fromtimestamp(now - 10, tz=timezone.utc).isoformat()
    snap3 = {
        "now": now,
        "idle": {"redqueen-1"},
        "unaccepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#2",
                "url": "https://github.com/SimonBarnett/bobiverse/issues/2",
                "ts": live_ts,
                "offered_to": "redqueen-1",
                "offered_ts": offer_ts,
            }
        ],
    }
    assert sd.detect_idle_with_work(snap3) == []
    # No idle seats: silent.
    assert (
        sd.detect_idle_with_work(
            {"now": now, "idle": [], "unaccepted": snap["unaccepted"]}
        )
        == []
    )


def test_fr6439_emit_findings_posts(tmp_path: Path, monkeypatch):
    _wake_env(monkeypatch)
    posts: list[dict] = []
    monkeypatch.setattr(
        sc,
        "_WAKE_HTTP_POST",
        lambda url, body, headers: posts.append(dict(body)) or {"ok": True},
    )
    now = 1_700_000_000.0
    findings = [
        {
            "id": "bored-latency",
            "key": "redqueen",
            "title": "stall:bored-latency:redqueen",
            "evidence": {"nick": "redqueen-1", "machine": "redqueen", "lag_s": 900},
        },
        {
            "id": "resync-fail",
            "key": "streak-3",
            "title": "stall:resync-fail:streak-3",
            "evidence": {"streak": 3, "status": 429},
        },
    ]
    acts = sc.emit_findings(tmp_path, findings, now=now)
    assert any(a.get("posted") for a in acts)
    events = {p.get("event") for p in posts}
    assert sc.EVENT_SEAT_DOWN in events
    assert sc.EVENT_RATE_LIMITED in events


def test_fr6439_heartbeat_once_per_day(tmp_path: Path, monkeypatch):
    _wake_env(monkeypatch)
    posts: list = []
    monkeypatch.setattr(
        sc,
        "_WAKE_HTTP_POST",
        lambda *a, **k: posts.append(1) or {"ok": True},
    )
    # 07:00 UTC on a fixed day
    import calendar
    from datetime import datetime, timezone

    dt = datetime(2026, 11, 10, 7, 0, 0, tzinfo=timezone.utc)
    now = calendar.timegm(dt.utctimetuple())
    r1 = sc.maybe_heartbeat(tmp_path, now=float(now))
    assert r1.get("posted") is True
    r2 = sc.maybe_heartbeat(tmp_path, now=float(now) + 3600)
    assert r2.get("skipped") == "already_today"
    assert len(posts) == 1


def test_fr6439_chair_stall_scan_wires_callbacks():
    src = (REPO / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    scan = src[src.find("def _stall_scan") :]
    assert "stall_callbacks" in scan
    assert "maybe_heartbeat" in scan
    assert "emit_findings" in scan


def test_fr6439_shop_listen_wires_giveup():
    src = (REPO / "common" / "scripts" / "shop_listen.py").read_text(encoding="utf-8")
    assert "emit_giveup" in src
    assert "stall_callbacks" in src


def test_fr6439_build_manifest_includes_stall_callbacks():
    build = (REPO / "jeeves" / "scripts" / "Build-Jeeves.ps1").read_text(encoding="utf-8")
    for name in ("stall_callbacks", "stall_detectors", "stall_filer"):
        assert name in build


def test_fr6439_detect_all_includes_idle_with_work():
    assert sd.detect_idle_with_work in sd.DETECTORS
