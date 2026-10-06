"""Hostile MRB #1337: offer_top must accept is_pull (FR #1313 wiring)."""
from __future__ import annotations

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


def test_offer_top_accepts_is_pull_and_purges_merged_pr_number(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1278",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1278",
                    "title": "canonical seat nick",
                    "line": "FR #1278",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1313",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1313",
                    "title": "real fr",
                    "line": "FR #1313",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    is_pull = lambda r, n: str(n) == "1278"
    st, job = gitclaim.offer_top(home, "marchhare-1", "#marchhare", is_pull=is_pull)
    assert st == "ok" and job is not None
    assert job["id"] == "#1313"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#1278" not in left


def test_offer_top_without_is_pull_kw_does_not_nameerror(tmp_path: Path):
    """Regression: body referenced is_pull before the kw existed (MRB #1337)."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#9",
                    "url": "https://github.com/o/a/issues/9",
                    "title": "plain issue",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_top(home, "n-1", "#n")
    assert st == "ok"
    assert job["id"] == "#9"


def test_assign_row_refuses_fr_that_is_pull(tmp_path: Path, monkeypatch):
    import bobreport
    import registered_machines

    digest = tmp_path / "digest"
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    registered_machines.save_registered(digest, {"marchhare", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None

    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1278",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1278",
                    "title": "was a pr",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, res = gitclaim.assign_row(
        home,
        "marchhare-12345",
        "SimonBarnett/bobiverse",
        "FR",
        "#1278",
        is_pull=lambda r, n: str(n) == "1278",
    )
    assert st == "refused"
    assert "pull" in str(res).lower()
