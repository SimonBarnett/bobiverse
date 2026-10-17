"""FR #4569: REST comments HTTP 403 falls back to GraphQL, then the same gate."""
from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import mrb_merge_gate as gate

PASS_BODY = "## MRB board\n\n**Verdict:** PASS\n"


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.github.com/repos/o/r/issues/1/comments",
        code,
        "err",
        Message(),
        io.BytesIO(b"secondary rate limit"),
    )


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_comments_from_graphql_payload_matches_rest_shape():
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "comments": {
                        "nodes": [
                            {
                                "body": PASS_BODY,
                                "createdAt": "2026-10-17T04:20:16Z",
                                "authorAssociation": "OWNER",
                                "author": {"login": "SimonBarnett"},
                            }
                        ]
                    }
                }
            }
        }
    }
    comments = gate.comments_from_graphql_payload(payload)
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""
    assert comments[0]["author_association"] == "OWNER"


def test_rest_403_uses_graphql_pass_board(monkeypatch):
    def urlopen(req, timeout=30):
        if getattr(req, "full_url", "") .endswith("/graphql") or str(getattr(req, "full_url", "")).endswith("/graphql"):
            return _Resp(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "comments": {
                                    "nodes": [
                                        {
                                            "body": PASS_BODY,
                                            "createdAt": "2026-10-17T04:20:16Z",
                                            "authorAssociation": "NONE",
                                            "author": {"login": "flamingo-63220"},
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            )
        raise _http_error(403)

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    comments = gate.fetch_issue_comments(
        "SimonBarnett/a-search", "3646", token="EXAMPLE_TOKEN", sleeper=lambda _s: None
    )
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_main_rest_403_graphql_pass_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(
        gate,
        "fetch_issue_comments",
        lambda *a, **k: [
            {
                "body": PASS_BODY,
                "created_at": "2026-10-17T04:20:16Z",
                "author_association": "NONE",
                "user": {"login": "flamingo-63220"},
            }
        ],
    )
    rc = gate.main(["SimonBarnett/a-search", "3646"])
    err = capsys.readouterr()
    assert rc == 0
    assert "merge allowed" in err.out


def test_rest_403_graphql_failure_stays_unknown(monkeypatch):
    def urlopen(req, timeout=30):
        raise _http_error(403)

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    try:
        gate.fetch_issue_comments(
            "o/r", "9", token="EXAMPLE_TOKEN", sleeper=lambda _s: None
        )
    except gate.CommentsUnavailable as exc:
        assert "HTTP 403" in str(exc)
        assert "not merge refused" in str(exc)
    else:
        raise AssertionError("expected CommentsUnavailable")
