"""FR #4571: GraphQL comment fallback pages until the PASS board or the last page."""
from __future__ import annotations

import json

import mrb_merge_gate as gate

PASS_BODY = "## MRB board\n\n**Verdict:** PASS\n"


def _page(nodes: list[dict], *, has_next: bool, cursor: str) -> dict:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "comments": {
                        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                        "nodes": nodes,
                    }
                }
            }
        }
    }


def _node(body: str) -> dict:
    return {
        "body": body,
        "createdAt": "2026-10-17T04:00:00Z",
        "authorAssociation": "NONE",
        "author": {"login": "flamingo-63220"},
    }


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_pages_until_pass_board_on_second_page(monkeypatch):
    calls: list[str | None] = []

    def urlopen(req, timeout=30):
        variables = json.loads(req.data.decode("utf-8"))["variables"]
        calls.append(variables.get("cursor"))
        if len(calls) == 1:
            filler = [_node(f"note {i}") for i in range(100)]
            return _Resp(_page(filler, has_next=True, cursor="CURSOR2"))
        return _Resp(_page([_node(PASS_BODY)], has_next=True, cursor="CURSOR3"))

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    comments = gate.fetch_comments_graphql("SimonBarnett/a-search", "3646", token="EXAMPLE_TOKEN")
    ok, reason = gate.evaluate_merge_gate(comments)
    assert calls == [None, "CURSOR2"]
    assert ok is True
    assert reason == ""
    assert len(comments) == 101


def test_stops_on_first_page_when_board_is_present(monkeypatch):
    calls = {"n": 0}

    def urlopen(req, timeout=30):
        calls["n"] += 1
        return _Resp(_page([_node(PASS_BODY)], has_next=True, cursor="MORE"))

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    comments = gate.fetch_comments_graphql("o/r", "1", token="EXAMPLE_TOKEN")
    assert calls["n"] == 1
    assert gate.evaluate_merge_gate(comments)[0] is True


def test_last_page_without_board_returns_comments(monkeypatch):
    def urlopen(req, timeout=30):
        return _Resp(_page([_node("no board")], has_next=False, cursor=""))

    monkeypatch.setattr(gate.urllib.request, "urlopen", urlopen)
    comments = gate.fetch_comments_graphql("o/r", "1", token="EXAMPLE_TOKEN")
    ok, reason = gate.evaluate_merge_gate(comments)
    assert ok is False
    assert "no MRB PASS board" in reason
