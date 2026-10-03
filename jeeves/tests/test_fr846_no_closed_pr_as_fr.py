"""FR #846: never offer/keep FR rows whose GitHub number is a pull request (open or closed)."""
from __future__ import annotations

import json
from pathlib import Path

import gitclaim


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def fetcher(table):
    def f(url):
        for k, v in table.items():
            if k in url:
                if isinstance(v, Exception):
                    raise v
                return v
        return []

    return f


def test_fr_row_offerable_rejects_pull_url():
    assert gitclaim.fr_row_offerable(
        {"task": "FR", "repo": "o/a", "id": "#10", "url": "https://github.com/o/a/issues/10"}
    )
    assert not gitclaim.fr_row_offerable(
        {"task": "FR", "repo": "o/a", "id": "#833", "url": "https://github.com/o/a/pull/833"}
    )
    # Non-FR rows are not gated by this helper.
    assert gitclaim.fr_row_offerable(
        {"task": "MRB", "repo": "o/a", "id": "#1", "url": "https://github.com/o/a/pull/1"}
    )


def test_offer_focus_top_skips_fr_with_pull_url(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#833",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/833",
                    "line": "FR #821: harden UAT gates",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#846",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/846",
                    "line": "Chair offered closed PR as FR",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert (job.get("task"), job.get("id")) == ("FR", "#846")


def test_prune_drops_fr_with_pull_url(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#833",
                    "url": "https://github.com/o/a/pull/833",
                    "seq": 1,
                },
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#10",
                    "url": "https://github.com/o/a/issues/10",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    out = gitclaim.prune_unassignable_queue(home)
    assert out.get("ok") is True
    left = gitclaim.load_unaccepted(home)
    assert [(r["task"], r["id"]) for r in left] == [("FR", "#10")]


def test_resync_drops_offered_fr_not_on_github_and_fr_matching_open_pr(tmp_path: Path):
    """Closed-PR phantom (#833 class): offered_to must not preserve a non-issue FR.

    Also: FR whose id is an open pull number must never stay queued as FR.
    """
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#833",
                    "seq": 1,
                    "offered_to": "marchhare-1",
                    "line": "closed PR phantom",
                },
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#50",
                    "seq": 2,
                    "line": "open PR number wrongly queued as FR",
                },
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#10",
                    "seq": 3,
                    "line": "real open issue",
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    table = {
        "o/a/issues": [
            {"number": 10, "title": "real", "state": "open"},
            {"number": 50, "title": "pr", "state": "open", "pull_request": {"url": "x"}},
        ],
        "o/a/pulls": [{"number": 50, "title": "pr", "body": "", "state": "open"}],
    }
    res = gitclaim.resync_from_github(home, ["o/a"], fetch_json=fetcher(table))
    assert res.get("ok") is True
    rows = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(home)}
    assert ("FR", "#10") in rows
    assert ("FR", "#833") not in rows
    assert ("FR", "#50") not in rows
    assert ("MRB", "#50") in rows
