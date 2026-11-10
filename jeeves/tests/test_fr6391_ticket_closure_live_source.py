"""FR #6391: real GitHub close source, webhook wake retry, chair schedule, build manifest."""
from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from repo_layout import REPO

_MON = REPO / "jeeves" / "tools" / "monitor"
if str(_MON) not in sys.path:
    sys.path.insert(0, str(_MON))

import ticket_closure as tc  # noqa: E402
from test_fr6064_ticket_closure_dedupe import STATE, _fx, _homes


@pytest.fixture(autouse=True)
def _no_real_wake(monkeypatch):
    """Never POST a real wake webhook from unit tests (host may set BOB wake URL)."""
    for name in (
        "JEEVES_TICKET_CLOSURE_WAKE_URL",
        "JEEVES_BOB_WAKE_URL",
        "JEEVES_TICKET_CLOSURE_WAKE_SECRET",
        "JEEVES_BOB_WAKE_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        tc,
        "_WAKE_HTTP_POST",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("real wake POST")),
    )




def _args(chair: Path, digest: Path) -> Namespace:
    return Namespace(
        chair_home=str(chair),
        digest_home=str(digest),
        dry_run=False,
        help_exit0=False,
    )


def test_fr6391_first_poll_seeds_cursor_no_history(tmp_path: Path, monkeypatch):
    """No poll_cursor: seed to now and do not fetch/replay historical closes."""
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_WAKE", raising=False)

    calls: list[str] = []

    def fetch(url: str, **_kw):
        calls.append(url)
        return [
            {
                "number": 1,
                "title": "ancient",
                "state": "closed",
                "closed_at": "2020-01-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 0
    assert payload.get("closed_count") == 0
    assert calls == []
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body.get("poll_cursor")
    assert "T" in body["poll_cursor"] and body["poll_cursor"].endswith("Z")


def test_fr6391_no_fixture_polls_github_mocked(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_WAKE", raising=False)

    # Seed a prior cursor so this cycle actually polls (first poll only seeds).
    ops = digest
    ops.mkdir(parents=True, exist_ok=True)
    (ops / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T11:00:00Z"}),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fetch(url: str, **_kw):
        calls.append(url)
        if "/issues?" in url:
            assert "since=2026-11-10T11:00:00Z" in url
            return [
                {
                    "number": 99,
                    "title": "done item",
                    "state": "closed",
                    "closed_at": "2026-11-10T12:00:00Z",
                    "pull_request": None,
                },
                {
                    "number": 100,
                    "title": "merged pr",
                    "state": "closed",
                    "closed_at": "2026-11-10T12:05:00Z",
                    "pull_request": {"merged_at": "2026-11-10T12:05:00Z"},
                    "merged_at": "2026-11-10T12:05:00Z",
                },
            ]
        return []

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("closed_count") == 2
    assert any(c.get("number") == 99 and c.get("kind") == "issue" for c in payload["closed"])
    assert any(c.get("number") == 100 and c.get("event") == "merged" for c in payload["closed"])
    assert any("api.github.com/repos/SimonBarnett/bobiverse/issues" in u for u in calls)
    assert payload.get("last_poll_at")
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body.get("poll_cursor") == "2026-11-10T12:05:00Z"
    assert body.get("last_poll_at")


def test_fr6391_wake_url_https_only(monkeypatch):
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "http://example.test/wake")
    assert tc._wake_url() == ""
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    assert tc._wake_url() == "https://example.test/wake"


def test_fr6391_dedupe_across_restarts(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)

    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T09:00:00Z"}),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        return [
            {
                "number": 7,
                "title": "x",
                "state": "closed",
                "closed_at": "2026-11-10T10:00:00Z",
            }
        ]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    p1, c1 = tc.check(_args(chair, digest))
    assert c1 == 1 and p1["closed_count"] == 1
    p2, c2 = tc.check(_args(chair, digest))
    assert c2 == 0 and p2["closed_count"] == 0


def test_fr6391_webhook_fail_keeps_pending_retry(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json", [
        {
            "kind": "issue",
            "event": "closed",
            "repo": "SimonBarnett/bobiverse",
            "number": 81,
            "closed_at": "2026-11-03T15:00:00Z",
            "delivery_id": "del-81",
        }
    ])
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE", "1")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "sekrit")

    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append({"url": url, "body": body, "headers": headers})
        raise ConnectionError("502")

    monkeypatch.setattr(tc, "_WAKE_HTTP_POST", post_wake)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("woke") == 0
    assert payload.get("pending_count") >= 1
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body.get("seen") in ({}, None)
    assert any("del-81" in k for k in (body.get("pending") or {}))
    # secret never persisted in state
    raw = (digest / STATE).read_text(encoding="utf-8")
    assert "sekrit" not in raw
    # Secret may travel in Authorization / X-Bob-Wake-Secret; never land in state.
    assert posts and posts[0]["headers"].get("Authorization")
    assert "sekrit" not in json.dumps(posts[0].get("body") or {})


def test_fr6391_webhook_success_posts_and_marks_seen(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json", [
        {
            "kind": "pr",
            "event": "merged",
            "repo": "SimonBarnett/bobiverse",
            "number": 42,
            "closed_at": "2026-11-10T11:00:00Z",
            "delivery_id": "del-42",
            "title": "fix",
        }
    ])
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_FIXTURE", str(fx))
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "sekrit")

    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append({"url": url, "body": body, "headers": dict(headers)})
        return {"ok": True, "status": 200}

    monkeypatch.setattr(tc, "_WAKE_HTTP_POST", post_wake)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("woke") == 1
    assert posts and posts[0]["url"] == "https://example.test/wake"
    assert "SimonBarnett/bobiverse#42" in posts[0]["body"].get("text", "")
    auth = posts[0]["headers"].get("Authorization") or posts[0]["headers"].get("X-Bob-Wake-Secret")
    assert auth
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert any("del-42" in k for k in (body.get("seen") or {}))
    assert body.get("pending") in ({}, None)
    assert body.get("last_wake_at")


def test_fr6391_build_manifest_includes_modules():
    build = (REPO / "jeeves" / "scripts" / "Build-Jeeves.ps1").read_text(encoding="utf-8")
    for name in ("ticket_closure", "wake_brief", "wake_grok_bot_bob"):
        assert name in build


def test_fr6391_chair_jobs_schedules_ticket_closure(tmp_path, monkeypatch):
    import chair_health as ch

    assert ch.TICKET_CLOSURE_S == 900.0  # FR #6405 backup poll
    logs: list[str] = []
    ran = {"n": 0}

    def fake_run(**_kw):
        ran["n"] += 1
        return {"ok": True, "closed_count": 0, "pending_count": 0, "woke": 0}

    monkeypatch.setattr(ch, "run_ticket_closure_cycle", fake_run)
    clk = type("C", (), {"t": 0.0})()
    clk.t = 0.0

    def clock():
        return clk.t

    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        announce=lambda *_: None,
        http=lambda *a, **k: (200, b""),
        token_loader=lambda: ("", "none"),
        clock=clock,
        sleep=lambda s: None,
        spawn=False,
        owners={"SimonBarnett"},
    )
    assert any("ticket-closure enabled" in ln for ln in logs)
    assert j.tick() is False
    clk.t += ch.FIRST_TICKET_CLOSURE_DELAY_S + 1
    assert j.tick() is True
    assert ran["n"] == 1
    clk.t += 30
    j.tick()
    assert ran["n"] == 1
    clk.t += ch.TICKET_CLOSURE_S
    j.tick()
    assert ran["n"] == 2


def test_fr6391_e2e_closed_pr_to_one_post(tmp_path: Path, monkeypatch):
    """Closed PR from mocked GitHub -> one wake POST."""
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "x")
    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T10:00:00Z"}),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        return [
            {
                "number": 6374,
                "title": "OpenCode finish",
                "state": "closed",
                "closed_at": "2026-11-10T10:36:40Z",
                "pull_request": {"merged_at": "2026-11-10T10:36:39Z"},
                "merged_at": "2026-11-10T10:36:39Z",
            }
        ]

    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append(body)
        return {"ok": True, "status": 200}

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    monkeypatch.setattr(tc, "_WAKE_HTTP_POST", post_wake)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload.get("woke") == 1
    assert len(posts) == 1
    assert "6374" in posts[0].get("text", "")
    assert posts[0].get("kind") == "pr"
