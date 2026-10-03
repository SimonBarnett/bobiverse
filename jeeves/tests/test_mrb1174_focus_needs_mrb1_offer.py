"""MRB #1174: offer needs-mrb1 under bobiverse focus; strict stays in-focus; keep pagination."""
from __future__ import annotations

import re

import gitclaim


def _fr(repo: str, n: int, labels=None, title: str = "FR: x"):
    return {
        "repo": repo,
        "task": "FR",
        "id": f"#{n}",
        "seq": n,
        "ts": "t",
        "line": f"FR {repo}#{n}",
        "title": title,
        "body": "",
        "labels": list(labels or ["feature-request"]),
        "state": "open",
    }


def test_strict_offers_needs_mrb1_bobiverse_not_club(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":["SimonBarnett/bobiverse"],"strict":true}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _fr("SimonBarnett/Club-Madeira", 2, ["feature-request"]),
                _fr(
                    "SimonBarnett/bobiverse",
                    1055,
                    ["needs-mrb1", "feature-request", "via-intake"],
                    title="FR: ionos fleet id pin",
                ),
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#1055"
    assert "bobiverse" in job["repo"]
    assert "needs-mrb1" in (job.get("labels") or [])


def test_non_strict_fallback_still_keeps_the_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":["SimonBarnett/bobiverse"],"strict":false}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _fr("SimonBarnett/Club-Madeira", 2, ["feature-request"]),
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "ok"
    assert "Club-Madeira" in job["repo"]


def test_pagination_helper_still_present():
    assert hasattr(gitclaim, "resync_from_github")
    src = open(gitclaim.__file__, encoding="utf-8").read()
    assert "def _fetch_all_pages" in src
    assert "max_pages" in src


def _issue(n: int):
    return {
        "number": n,
        "title": "FR: x",
        "html_url": f"https://github.com/o/a/issues/{n}",
        "labels": [{"name": "feature-request"}],
        "body": "",
        "user": {"login": "u"},
        "pull_request": None,
    }


def _page_num(url: str) -> int:
    m = re.search(r"[?&]page=(\d+)", url)
    return int(m.group(1)) if m else 1


def test_resync_still_paginates_past_100(tmp_path, monkeypatch):
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

    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    assert any("page=2" in u for u in pages_seen)
    ids = {r["id"] for r in gitclaim.load_unaccepted(tmp_path)}
    assert "#105" in ids
