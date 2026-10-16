"""FR #4467: comment-list HTTP 403/429 is not an owner hold and not merge refused."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import pytest

import mrb_merge_gate as gate

PASS_BOARD = {
    "author_association": "OWNER",
    "created_at": "2026-10-16T20:00:00Z",
    "body": "## MRB board\n\n**Verdict:** PASS\n",
}
OWNER_HOLD = {
    "author_association": "OWNER",
    "created_at": "2026-10-16T19:00:00Z",
    "body": "on hold do not merge this pr",
}


def _http_error(code: int, body: bytes = b"rate limit", retry_after: str | None = None):
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://api.github.com/repos/o/r/issues/1/comments",
        code,
        "err",
        hdrs,
        io.BytesIO(body),
    )


class _Resp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fr4467_403_retries_then_allows_pass_board(monkeypatch):
    """A rate-limit 403 is retried; a later PASS board still allows merge."""
    calls = {"n": 0}

    def urlopen(req, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(403, b'{"message":"secondary rate limit"}')
        return _Resp([PASS_BOARD])

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    sleeps: list[float] = []
    comments = gate.fetch_issue_comments(
        "o/r", "1", token="EXAMPLE_TOKEN", sleeper=lambda s: sleeps.append(s)
    )
    assert calls["n"] == 2
    assert sleeps
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_fr4467_403_exhausted_is_unknown_not_refused(monkeypatch):
    """After retries, 403 is comments-unknown, not FR #3928 merge refused."""

    def urlopen(req, timeout=30):
        raise _http_error(403, b"You have exceeded a secondary rate limit")

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    with pytest.raises(gate.CommentsUnavailable) as caught:
        gate.fetch_issue_comments(
            "o/r", "9", token="EXAMPLE_TOKEN", sleeper=lambda _s: None
        )
    msg = str(caught.value)
    assert "HTTP 403" in msg
    assert "not an owner hold" in msg
    assert "not merge refused" in msg
    assert not msg.startswith("FR #3928 merge refused")


def test_fr4467_main_403_exits_3(monkeypatch, capsys):
    """CLI exit 3 means unknown comments, not exit 2 merge refused."""

    def urlopen(req, timeout=30):
        raise _http_error(403, b"secondary rate limit")

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("GH_TOKEN", "EXAMPLE_TOKEN")
    rc = gate.main(["SimonBarnett/bobiverse", "2172"])
    err = capsys.readouterr().err
    assert rc == 3
    assert "not merge refused" in err
    assert not err.startswith("FR #3928 merge refused")


def test_fr4467_retry_after_is_capped(monkeypatch):
    """Retry-After of minutes must not stall the seat; cap each wait."""
    calls = {"n": 0}

    def urlopen(req, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(403, b"secondary rate limit", retry_after="120")
        return _Resp([PASS_BOARD])

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    sleeps: list[float] = []
    gate.fetch_issue_comments(
        "o/r", "1", token="EXAMPLE_TOKEN", sleeper=lambda s: sleeps.append(s)
    )
    assert calls["n"] == 3
    assert sleeps == [2.0, 2.0]


def test_fr4467_429_exhausted_is_unknown(monkeypatch):
    def urlopen(req, timeout=30):
        raise _http_error(429, b"rate limit", retry_after="1")

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    with pytest.raises(gate.CommentsUnavailable) as caught:
        gate.fetch_issue_comments(
            "o/r", "9", token="EXAMPLE_TOKEN", sleeper=lambda _s: None
        )
    assert "HTTP 429" in str(caught.value)
    assert "not merge refused" in str(caught.value)


def test_fr4467_401_stays_hard_error(monkeypatch):
    """Auth failure is still an error, not comments-unknown."""

    def urlopen(req, timeout=30):
        raise _http_error(401, b"bad credentials")

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError) as caught:
        gate.fetch_issue_comments(
            "o/r", "9", token="EXAMPLE_TOKEN", sleeper=lambda _s: None
        )
    assert not isinstance(caught.value, gate.CommentsUnavailable)
    assert "HTTP 401" in str(caught.value)


def test_fr4467_owner_hold_still_exit_2(monkeypatch, capsys):
    """A real owner hold still refuses merge (exit 2) after comments load."""
    monkeypatch.setattr(
        gate, "fetch_issue_comments", lambda *a, **k: [OWNER_HOLD, PASS_BOARD]
    )
    rc = gate.main(["o/r", "9"])
    err = capsys.readouterr().err
    assert rc == 2
    assert err.startswith("FR #3928 merge refused")
