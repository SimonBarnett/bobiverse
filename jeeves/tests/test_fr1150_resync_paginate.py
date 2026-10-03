"""PR #1149 / harvest #1150: paginate resync; preserve intentional needs_human."""
from __future__ import annotations

import re

import gitclaim


def _issue(n: int, title: str = "FR: x", labels=None):
    return {
        "number": n,
        "title": title,
        "html_url": f"https://github.com/o/a/issues/{n}",
        "labels": [{"name": x} for x in (labels or ["feature-request"])],
        "body": "",
        "user": {"login": "u"},
        "pull_request": None,
    }


def _page_num(url: str) -> int:
    m = re.search(r"[?&]page=(\d+)", url)
    return int(m.group(1)) if m else 1


def test_resync_paginates_past_100_open_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    pages_seen = []

    def fetch(url: str):
        pages_seen.append(url)
        if "/pulls" in url:
            return []
        page = _page_num(url)
        if page == 1:
            return [_issue(i) for i in range(1, 101)]
        if page == 2:
            return [_issue(i) for i in range(101, 106)]
        return []

    res = gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    assert any("page=2" in u for u in pages_seen)
    assert any("page=1" in u for u in pages_seen)
    rows = gitclaim.load_unaccepted(tmp_path)
    ids = {r["id"] for r in rows}
    assert "#105" in ids
    assert "#1" in ids
    assert res.get("added", 0) >= 1


def test_resync_drops_done_when_github_still_open(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#50",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )

    def fetch(url: str):
        if "/pulls" in url:
            return []
        return [_issue(50, title="FR: still open")]

    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    doc = gitclaim.load_queue(tmp_path)
    assert not any(r.get("id") == "#50" for r in doc.get("done") or [])
    assert any(r.get("id") == "#50" for r in doc.get("unaccepted") or [])


def test_resync_keeps_needs_human_after_two_giveups(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#7",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR o/a#7",
                    "title": "FR: gated",
                    "labels": ["feature-request"],
                    "needs_human": True,
                    "giveup_count": 2,
                },
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#8",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR o/a#8",
                    "title": "FR: stale flag",
                    "labels": ["feature-request"],
                    "needs_human": True,
                    "giveup_count": 0,
                },
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/pulls" in url:
            return []
        return [_issue(7, title="FR: gated"), _issue(8, title="FR: stale flag")]

    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    rows = {r["id"]: r for r in gitclaim.load_unaccepted(tmp_path)}
    assert rows["#7"].get("needs_human") is True
    assert not rows["#8"].get("needs_human")
