"""FR #6400: per-repo poll cursors + pagination beyond per_page=50."""
from __future__ import annotations

import json
import re
import sys
from argparse import Namespace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def _focus_two(digest: Path) -> None:
    (digest / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "repos": {
                    "SimonBarnett/bobiverse": {"priority": 1},
                    "SimonBarnett/a-search": {"priority": 2},
                },
            }
        ),
        encoding="utf-8",
    )


def _closed_item(number: int, closed_at: str) -> dict:
    return {
        "number": number,
        "title": f"n{number}",
        "state": "closed",
        "closed_at": closed_at,
        "pull_request": None,
    }


def test_fr6400_pagination_fetches_all_pages(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursor": "2026-11-01T00:00:00Z",
                "poll_cursors": {"SimonBarnett/bobiverse": "2026-11-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    pages: list[int] = []

    def fetch(url: str, **_kw):
        qs = parse_qs(urlparse(url).query)
        page = int((qs.get("page") or ["1"])[0])
        pages.append(page)
        if page == 1:
            return [_closed_item(i, f"2026-11-01T00:{i:02d}:00Z") for i in range(1, 51)]
        if page == 2:
            return [
                _closed_item(51, "2026-11-01T01:00:00Z"),
                _closed_item(52, "2026-11-01T01:01:00Z"),
                _closed_item(53, "2026-11-01T01:02:00Z"),
            ]
        return []

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    monkeypatch.setattr(tc, "POLL_PER_PAGE", 50)
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload["closed_count"] == 53
    assert pages == [1, 2]
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["poll_cursors"]["SimonBarnett/bobiverse"] == "2026-11-01T01:02:00Z"
    assert body["poll_cursor"] == "2026-11-01T01:02:00Z"


def test_fr6400_per_repo_cursors_isolated(tmp_path: Path, monkeypatch):
    """Repo A page2 must not be skipped when repo B has a later closed_at on page1."""
    chair, digest = _homes(tmp_path)
    _focus_two(digest)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursor": "2026-11-01T00:00:00Z",
                "poll_cursors": {
                    "SimonBarnett/bobiverse": "2026-11-01T00:00:00Z",
                    "SimonBarnett/a-search": "2026-11-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        path = urlparse(url).path
        qs = parse_qs(urlparse(url).query)
        page = int((qs.get("page") or ["1"])[0])
        if "/SimonBarnett/bobiverse/" in path:
            if page == 1:
                # 50 items; newest on this page is T50 (before B's close).
                return [
                    _closed_item(i, f"2026-11-01T00:{i:02d}:00Z") for i in range(1, 51)
                ]
            if page == 2:
                return [_closed_item(99, "2026-11-01T02:00:00Z")]
            return []
        if "/SimonBarnett/a-search/" in path:
            # Later than A's page1 max, earlier than A's page2.
            return [_closed_item(7, "2026-11-01T01:00:00Z")]
        return []

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    nums = {(c["repo"], c["number"]) for c in payload["closed"]}
    assert ("SimonBarnett/bobiverse", 99) in nums
    assert ("SimonBarnett/a-search", 7) in nums
    assert payload["closed_count"] == 52  # 50 + 1 + 1
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["poll_cursors"]["SimonBarnett/bobiverse"] == "2026-11-01T02:00:00Z"
    assert body["poll_cursors"]["SimonBarnett/a-search"] == "2026-11-01T01:00:00Z"


def test_fr6400_waiting_filter_advances_cursor_from_all_pages(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / "ticket-closure-waiting.json").write_text(
        json.dumps({"waiting_on": ["SimonBarnett/bobiverse#100"]}),
        encoding="utf-8",
    )
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursors": {"SimonBarnett/bobiverse": "2026-11-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        qs = parse_qs(urlparse(url).query)
        page = int((qs.get("page") or ["1"])[0])
        if page == 1:
            return [_closed_item(i, f"2026-11-01T00:{i:02d}:00Z") for i in range(1, 51)]
        return [_closed_item(100, "2026-11-01T03:00:00Z")]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload["closed_count"] == 1
    assert payload["closed"][0]["number"] == 100
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    # Cursor advanced past non-waiting page1 items too.
    assert body["poll_cursors"]["SimonBarnett/bobiverse"] == "2026-11-01T03:00:00Z"


def test_fr6400_link_rel_next_pagination(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps(
            {
                "seen": {},
                "pending": {},
                "poll_cursors": {"SimonBarnett/bobiverse": "2026-11-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    seen_urls: list[str] = []

    def fetch(url: str, **_kw):
        seen_urls.append(url)
        if "page=1" in url or ("page=" not in url and "since=" in url):
            items = [_closed_item(i, f"2026-11-01T00:{i:02d}:00Z") for i in range(1, 51)]
            nxt = re.sub(r"page=\d+", "page=2", url)
            if "page=" not in nxt:
                nxt = url + "&page=2"
            return items, f'<{nxt}>; rel="next"'
        return [_closed_item(60, "2026-11-01T04:00:00Z")], None

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1
    assert payload["closed_count"] == 51
    assert len(seen_urls) == 2
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["poll_cursors"]["SimonBarnett/bobiverse"] == "2026-11-01T04:00:00Z"


def test_fr6400_legacy_poll_cursor_migrates(tmp_path: Path, monkeypatch):
    chair, digest = _homes(tmp_path)
    monkeypatch.delenv("JEEVES_TICKET_CLOSURE_FIXTURE", raising=False)
    (digest / STATE).write_text(
        json.dumps({"seen": {}, "pending": {}, "poll_cursor": "2026-11-09T12:00:00Z"}),
        encoding="utf-8",
    )

    def fetch(url: str, **_kw):
        assert "since=2026-11-09T12:00:00Z" in url
        return [_closed_item(3, "2026-11-09T13:00:00Z")]

    monkeypatch.setattr(tc, "_GITHUB_FETCH", fetch)
    monkeypatch.setattr(tc, "_GITHUB_TOKEN", lambda: ("tok", "test"))
    payload, code = tc.check(_args(chair, digest))
    assert code == 1 and payload["closed_count"] == 1
    body = json.loads((digest / STATE).read_text(encoding="utf-8"))
    assert body["poll_cursors"]["SimonBarnett/bobiverse"] == "2026-11-09T13:00:00Z"