"""FR #6405: no-token warn + webhook-first closes + poll backup dedupe."""
from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

_MON = REPO / "jeeves" / "tools" / "monitor"
if str(_MON) not in sys.path:
    sys.path.insert(0, str(_MON))

import ticket_closure as tc  # noqa: E402
from test_fr6064_ticket_closure_dedupe import STATE, _homes


def _args(chair: Path, digest: Path) -> Namespace:
    return Namespace(
        chair_home=str(chair),
        digest_home=str(digest),
        dry_run=False,
        help_exit0=False,
    )


@pytest.fixture(autouse=True)
def _reset_warn(monkeypatch):
    monkeypatch.setattr(tc, "_LAST_NO_TOKEN_WARN_AT", 0.0)
    for name in (
        "JEEVES_TICKET_CLOSURE_WAKE_URL",
        "JEEVES_BOB_WAKE_URL",
        "JEEVES_TICKET_CLOSURE_WAKE_SECRET",
        "JEEVES_BOB_WAKE_SECRET",
        "JEEVES_TICKET_CLOSURE_FIXTURE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_fr6405_no_token_warns_and_skips_fetch(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T10:00:00Z"}),
        encoding="utf-8",
    )
    logs: list[str] = []
    monkeypatch.setattr(tc, "_LOG", logs.append)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("", "none"))
    calls: list[str] = []

    def fetch(url: str, **_kw):
        calls.append(url)
        return []

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_CLOCK", lambda: 1000.0)
    payload, _code = tc.check(_args(chair, digest))
    assert calls == []
    assert payload["ticket_closure_token_source"] == "none"
    assert payload["token_source"] == "none"
    assert payload["no_token_warned"] is True
    assert any("no GitHub token" in x for x in logs)
    # rate-limit: second call within window does not warn again
    payload2, _ = tc.check(_args(chair, digest))
    assert payload2["no_token_warned"] is False
    assert sum(1 for x in logs if "no GitHub token" in x) == 1


def test_fr6405_webhook_close_one_wake(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "x")
    posts: list[dict] = []

    def post_wake(url: str, body: dict, headers: dict):
        posts.append(body)
        return {"ok": True, "status": 200}

    monkeypatch.setattr(tc, "_WAKE_HTTP_POST", post_wake)
    payload = {
        "action": "closed",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "pull_request": {
            "number": 6405,
            "title": "x",
            "merged": True,
            "merged_at": "2026-11-10T12:00:00Z",
            "closed_at": "2026-11-10T12:00:01Z",
        },
    }
    out = tc.ingest_github_webhook(
        digest, "pull_request", payload, delivery_id="del-6405", chair_home=chair
    )
    assert out["accepted"] is True
    assert out["woke"] == 1
    assert len(posts) == 1
    assert "6405" in posts[0].get("text", "")


def test_fr6405_webhook_then_poll_same_close_one_wake(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "x")
    posts: list[dict] = []
    monkeypatch.setattr(
        tc,
        "_WAKE_HTTP_POST",
        lambda url, body, headers: posts.append(body) or {"ok": True, "status": 200},
    )
    wh = {
        "action": "closed",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 77,
            "title": "done",
            "closed_at": "2026-11-10T12:00:00Z",
        },
    }
    assert tc.ingest_github_webhook(digest, "issues", wh, delivery_id="d1", chair_home=chair)[
        "woke"
    ] == 1
    assert len(posts) == 1

    def fetch(url: str, **_kw):
        return [
            {
                "number": 77,
                "title": "done",
                "state": "closed",
                "closed_at": "2026-11-10T12:00:00Z",
            }
        ]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    (digest / STATE).write_text(
        (digest / STATE).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # ensure cursor so poll runs
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    body["poll_cursor"] = "2026-11-10T11:00:00Z"
    (digest / STATE).write_text(json.dumps(body), encoding="utf-8")
    payload, code = tc.check(_args(chair, digest))
    assert payload["closed_count"] == 0
    assert len(posts) == 1


def test_fr6405_poll_catches_missed_webhook(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_URL", "https://example.test/wake")
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_WAKE_SECRET", "x")
    posts: list[dict] = []
    monkeypatch.setattr(
        tc,
        "_WAKE_HTTP_POST",
        lambda url, body, headers: posts.append(body) or {"ok": True, "status": 200},
    )
    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T10:00:00Z"}),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        return [
            {
                "number": 88,
                "title": "missed",
                "state": "closed",
                "closed_at": "2026-11-10T10:30:00Z",
            }
        ]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "env"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload["closed_count"] == 1
    assert len(posts) == 1
    assert payload["token_source"] == "env"


def test_fr6405_interval_default_and_override(monkeypatch):
    import chair_health as ch

    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_S", raising=False)
    assert ch.TICKET_CLOSURE_S == 900.0
    assert ch.ticket_closure_interval_s() == 900.0
    monkeypatch.setenv("JEEVES_TICKET_CLOSURE_S", "120")
    assert ch.ticket_closure_interval_s() == 120.0


def test_fr6405_docs_and_bobcallback_hook():
    docs = (ROOT / "jeeves/docs/wake-grok-bot-bob.md").read_text(encoding="utf-8")
    assert "FR #6405" in docs or "#6405" in docs
    assert "900" in docs or "15 min" in docs
    assert "github.token" in docs or "GITHUB_TOKEN" in docs
    bc = (ROOT / "common/scripts/bobcallback.py").read_text(encoding="utf-8")
    assert "_ticket_closure_from_git" in bc
    assert "ingest_github_webhook" in bc
