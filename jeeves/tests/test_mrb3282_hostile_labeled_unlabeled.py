"""MRB #3282 hostile pins for FR #3275 labeled|unlabeled webhook completeness."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"


def _issue_payload(action: str, num: int, *, labels=None, title: str | None = None, state: str = "open", is_pr: bool = False):
    issue = {
        "number": num,
        "title": title or f"issue {num}",
        "body": "body",
        "state": state,
        "labels": [{"name": n} for n in (labels or [])],
    }
    if is_pr:
        issue["pull_request"] = {"url": f"https://api.github.com/repos/{REPO}/pulls/{num}"}
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "label": {"name": (labels or ["x"])[-1] if action in ("labeled", "unlabeled") else "x"},
        "issue": issue,
    }


def _pr_payload(action: str, num: int, *, labels=None):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "label": {"name": (labels or ["x"])[-1] if action in ("labeled", "unlabeled") else "x"},
        "pull_request": {
            "number": num,
            "title": f"pr {num}",
            "body": f"Closes {REPO}#1",
            "merged": False,
            "draft": False,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/{num}",
            "labels": [{"name": n} for n in (labels or [])],
        },
    }


def _seed_fr(home: Path, num: int, *, labels=None, title: str = "seed fr"):
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id=f"#{num}",
        event="issues",
        action="opened",
        line=title,
        title=title,
        body="body",
        labels=tuple(labels or ()),
        state="open",
    )
    assert gitclaim.apply_queue_event(home, claim) in ("added", "duplicate")


def test_issues_pull_request_blob_labeled_returns_none():
    """GitHub issues events for PR threads must not invent an FR label claim."""
    claim = gitclaim.claim_from_payload(
        "issues",
        _issue_payload("labeled", 77, labels=["feature-request"], is_pr=True),
    )
    assert claim is None


def test_pr_labeled_does_not_invent_mrb_row(tmp_path: Path):
    """MRB label events mutate existing rows only — never invent from labeled alone."""
    out = bobreport.apply_git_webhook(
        tmp_path,
        "pull_request",
        _pr_payload("labeled", 88, labels=["harvest-lesson"]),
    )
    assert out.ok, out.err
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("MRB", "#88") not in ids


def test_unlabeled_clears_to_empty_labels(tmp_path: Path):
    """Empty remaining labels after unlabeled must write [] (not leave stale names)."""
    _seed_fr(tmp_path, 99, labels=["feature-request", "skill"], title="clear me")
    out = bobreport.apply_git_webhook(
        tmp_path,
        "issues",
        _issue_payload("unlabeled", 99, labels=[], title="clear me"),
    )
    assert out.ok, out.err
    rows = [r for r in gitclaim.load_unaccepted(tmp_path) if r["id"] == "#99" and r["task"] == "FR"]
    assert len(rows) == 1
    assert list(rows[0].get("labels") or []) == []


def test_labeled_missing_fr_backfills_unaccepted(tmp_path: Path):
    """If opened was missed, a later labeled event may add the FR (webhook completeness)."""
    out = bobreport.apply_git_webhook(
        tmp_path,
        "issues",
        _issue_payload("labeled", 101, labels=["feature-request"], title="late label"),
    )
    assert out.ok, out.err
    rows = [r for r in gitclaim.load_unaccepted(tmp_path) if r["id"] == "#101" and r["task"] == "FR"]
    assert len(rows) == 1
    assert set(rows[0].get("labels") or []) == {"feature-request"}
