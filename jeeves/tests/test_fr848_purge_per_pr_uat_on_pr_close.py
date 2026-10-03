"""FR #848: closing/merging a PR must purge leftover UAT for that PR id (mrb-fix class)."""
from __future__ import annotations

from pathlib import Path

import gitclaim


REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_merged_mrb_fix_purges_leftover_uat_for_pr_id(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#835",
                    "repo_uat": True,  # poisoned flag + wrong id
                    "line": "mrb-808-fix: rebase",
                    "title": "mrb-808-fix: rebase",
                    "seq": 1,
                },
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#10",
                    "url": f"https://github.com/{REPO}/issues/10",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 835,
                "title": "mrb-808-fix: rebase FR #795",
                "body": "Refs #808",
                "merged": True,
                "html_url": f"https://github.com/{REPO}/pull/835",
            },
        },
    )
    assert claim is not None
    assert gitclaim.is_mrb_fix_pr_title(str(claim.title or claim.line or ""))
    assert gitclaim.apply_queue_event(home, claim) in ("updated", "removed", "noop")
    rows = gitclaim.load_unaccepted(home)
    assert not any(
        str(r.get("task") or "").upper() == "UAT" and str(r.get("id") or "") == "#835" for r in rows
    )
    assert any(str(r.get("id") or "") == "#10" for r in rows)


def test_closed_unmerged_pr_also_purges_uat_for_pr_id(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#99",
                    "line": "stale",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 99,
                "title": "wip",
                "body": "",
                "merged": False,
                "html_url": f"https://github.com/{REPO}/pull/99",
            },
        },
    )
    assert claim is not None
    gitclaim.apply_queue_event(home, claim)
    rows = gitclaim.load_unaccepted(home)
    assert not any(str(r.get("task") or "").upper() == "UAT" for r in rows)


def test_prune_drops_offered_poisoned_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#835",
                    "repo_uat": True,
                    "offered_to": "marchhare-1",
                    "line": "mrb-808-fix",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    out = gitclaim.prune_unassignable_queue(home)
    assert out.get("ok") is True
    assert gitclaim.load_unaccepted(home) == []
