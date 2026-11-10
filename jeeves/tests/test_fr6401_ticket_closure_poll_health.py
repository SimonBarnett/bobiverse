"""FR #6401: poll_outcome / last_poll_ok_at vs failed or skipped polls."""
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
from test_fr6064_ticket_closure_dedupe import STATE, _homes


def _args(chair: Path, digest: Path) -> Namespace:
    return Namespace(
        chair_home=str(chair),
        digest_home=str(digest),
        dry_run=False,
        help_exit0=False,
    )


@pytest.fixture(autouse=True)
def _no_real_wake(monkeypatch):
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


def test_fr6401_skipped_no_token_keeps_last_ok(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursor": "2026-11-10T10:00:00Z",
                "last_poll_ok_at": 100.0,
                "poll_outcome": "ok",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("", "none"))
    monkeypatch.setattr(tc, "_CLOCK", lambda: 200.0)
    payload, _code = tc.check(_args(chair, digest))
    assert payload["poll_outcome"] == "skipped_no_token"
    assert payload["last_poll_error"] == "no_github_token"
    assert payload["last_poll_at"] == 200.0
    assert payload["last_poll_ok_at"] == 100.0
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["poll_outcome"] == "skipped_no_token"
    assert body["last_poll_ok_at"] == 100.0
    assert body["last_poll_error"] == "no_github_token"


def test_fr6401_repos_failed_does_not_advance_ok(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursor": "2026-11-10T10:00:00Z",
                "last_poll_ok_at": 50.0,
            }
        ),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        raise ConnectionError("boom")

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    monkeypatch.setattr(tc, "_CLOCK", lambda: 80.0)
    payload, _code = tc.check(_args(chair, digest))
    assert payload["poll_outcome"] == "repos_failed"
    assert payload["last_poll_ok_at"] == 50.0
    assert payload["last_poll_error"]
    assert "ConnectionError" in payload["last_poll_error"]
    assert payload["closed_count"] == 0


def test_fr6401_ok_poll_sets_last_ok_at(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-10T10:00:00Z"}),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        return [
            {
                "number": 9,
                "title": "x",
                "state": "closed",
                "closed_at": "2026-11-10T11:00:00Z",
            }
        ]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    monkeypatch.setattr(tc, "_CLOCK", lambda: 999.0)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload["poll_outcome"] == "ok"
    assert payload["last_poll_ok_at"] == 999.0
    assert payload.get("last_poll_error") in (None, "")
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["last_poll_ok_at"] == 999.0
    assert body["poll_outcome"] == "ok"
    assert "last_poll_error" not in body


def test_fr6401_seeded_first_poll_is_ok(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    monkeypatch.setattr(tc, "_CLOCK", lambda: 42.0)
    payload, code = tc.check(_args(chair, digest))
    assert code == 0
    assert payload["poll_outcome"] == "seeded"
    assert payload["last_poll_ok_at"] == 42.0


def test_fr6401_status_line_includes_poll_fields():
    # Lightweight shape check against irc_agent source (avoids full chair fixture).
    from repo_layout import ROOT

    text = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "poll={outcome}" in text or 'poll={outcome}' in text or "poll=" in text
    assert "last_ok=" in text
    assert "last_poll_error" in text
