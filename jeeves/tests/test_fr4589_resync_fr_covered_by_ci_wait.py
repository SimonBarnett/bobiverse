"""FR #4589: resync must not queue FR when an open Closes-PR is skipped as ci-wait."""
from __future__ import annotations

import gitclaim
import mrb_merge_on_green

REPO = "SimonBarnett/a-search"
PASS_SHA = "a" * 40


def _issue(n: int, title: str = "work"):
    return {
        "number": n,
        "title": title,
        "body": "implement",
        "state": "open",
        "labels": [{"name": "feature-request"}],
    }


def _pr(n: int, *, closes: int, sha: str = PASS_SHA, auto_merge=None, state: str = "open"):
    return {
        "number": n,
        "title": f"fix(#{closes})",
        "body": f"Closes {REPO}#{closes}\n",
        "html_url": f"https://github.com/{REPO}/pull/{n}",
        "state": state,
        "draft": False,
        "auto_merge": auto_merge,
        "head": {"sha": sha},
        "user": {"login": "u"},
    }


def _fetch(issues, prs, *, closed_prs=None):
    def fetch_json(url: str):
        if "state=closed" in url and "/pulls" in url:
            return list(closed_prs or [])
        if "/pulls" in url:
            return list(prs)
        if "/issues" in url:
            return list(issues)
        return []

    return fetch_json


def test_ci_wait_open_closes_keeps_fr_out_of_unaccepted(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "repo_archived_for_queue", lambda *a, **k: False)
    mrb_merge_on_green.enqueue(
        tmp_path,
        repo=REPO,
        pr="3665",
        pass_sha=PASS_SHA,
        url=f"https://github.com/{REPO}/pull/3665",
    )
    # Pre-seed a stale FR that resync must prune.
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#3462",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "url": f"https://github.com/{REPO}/issues/3462",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    pr = _pr(3665, closes=3462, auto_merge={"merge_method": "merge"})
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_issue(3462)], [pr]),
        token="FAKE_TOKEN",
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "FR" and str(r.get("id") or "") in ("#3462", "3462")
        for r in rows
        if isinstance(r, dict)
    )
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == "#3665"
        for r in rows
        if isinstance(r, dict)
    )


def test_fr_returns_when_covering_pr_closed_unmerged(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "repo_archived_for_queue", lambda *a, **k: False)
    # First pass: ci-wait cover, no FR.
    mrb_merge_on_green.enqueue(
        tmp_path,
        repo=REPO,
        pr="3665",
        pass_sha=PASS_SHA,
        url=f"https://github.com/{REPO}/pull/3665",
    )
    gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch(
            [_issue(3462)],
            [_pr(3665, closes=3462, auto_merge={"merge_method": "merge"})],
        ),
        token="FAKE_TOKEN",
    )
    assert not any(
        str(r.get("task") or "").upper() == "FR"
        for r in gitclaim.load_unaccepted(tmp_path)
        if isinstance(r, dict)
    )
    # Covering PR closed unmerged: FR must come back.
    closed = _pr(3665, closes=3462, auto_merge=None, state="closed")
    closed["merged_at"] = None
    gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_issue(3462)], [], closed_prs=[closed]),
        token="FAKE_TOKEN",
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(
        str(r.get("task") or "").upper() == "FR" and str(r.get("id") or "") == "#3462"
        for r in rows
        if isinstance(r, dict)
    )


def test_open_closes_helper_matches_norm_id():
    assert gitclaim.fr_superseded_by_open_closes_pr(
        REPO, "3462", {REPO: {"#3462"}}
    )
    assert gitclaim.fr_superseded_by_open_closes_pr(
        REPO, "#3462", {REPO: {"#3462"}}
    )
    assert not gitclaim.fr_superseded_by_open_closes_pr(
        REPO, "#9999", {REPO: {"#3462"}}
    )
