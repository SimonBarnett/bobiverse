"""FR #5500: never offer docs/mrb-* PRs as MRB (first-level pin or pin-of-pin).

Chair offered MRB bobiverse#5499 head docs/mrb-5215. FR #4917 only skipped
lesson-of-lesson / pin-of-pin; first-level docs/mrb still queued. Skip all
docs/mrb-* at offer, webhook, resync, and claim_from_github_issue.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"


def _docs_mrb_row(**extra):
    row = {
        "task": "MRB",
        "repo": REPO,
        "id": "#5499",
        "url": f"https://github.com/{REPO}/pull/5499",
        "title": "docs/mrb-5215: pin harvest skip after harvest-lesson MRB",
        "head": "docs/mrb-5215",
        "state": "open",
    }
    row.update(extra)
    return row


def test_fr5500_docs_mrb_title_not_offerable():
    why = gitclaim.mrb_row_not_offerable_reason(_docs_mrb_row())
    assert why == "docs_mrb_pin"
    assert gitclaim.mrb_row_offerable(_docs_mrb_row()) is False


def test_fr5500_docs_mrb_head_only_not_offerable():
    row = _docs_mrb_row(title="pin harvest skip after harvest-lesson MRB")
    assert gitclaim.is_docs_mrb_pin_pr(
        title=row["title"], head_ref=row["head"]
    )
    assert gitclaim.mrb_row_not_offerable_reason(row) == "docs_mrb_pin"
    assert gitclaim.mrb_row_offerable(row) is False


def test_fr5500_product_pr_still_offerable():
    row = {
        "task": "MRB",
        "repo": REPO,
        "id": "#5478",
        "url": f"https://github.com/{REPO}/pull/5478",
        "title": "FR #5468: HIGH_PRIORITY_REPOS is bobiverse plus a-search",
        "head": "fr-5468",
        "state": "open",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True


def test_fr5500_webhook_opened_docs_mrb_does_not_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 5499,
                "title": "docs/mrb-5215: pin harvest skip after harvest-lesson MRB",
                "body": "Closes SimonBarnett/bobiverse#5215",
                "draft": False,
                "html_url": f"https://github.com/{REPO}/pull/5499",
                "head": {"ref": "docs/mrb-5215"},
            },
        },
    )
    assert claim is None


def test_fr5500_claim_from_github_issue_docs_mrb_none():
    issue = {
        "number": 5499,
        "title": "docs/mrb-5215: pin harvest skip after harvest-lesson MRB",
        "body": "pin",
        "state": "open",
        "html_url": f"https://github.com/{REPO}/pull/5499",
        "pull_request": {},
        "draft": False,
        "labels": [],
    }
    assert gitclaim.claim_from_github_issue(REPO, issue) is None


def test_fr5500_enqueue_docs_mrb_skipped(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)

    def fetch_issue(_repo, _num):
        return {
            "number": 5499,
            "title": "docs/mrb-5215: pin harvest skip after harvest-lesson MRB",
            "body": "pin",
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/5499",
            "pull_request": {},
            "draft": False,
            "labels": [],
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "5499", fetch_issue=fetch_issue, home=home
    )
    assert status == "refused"
    assert "not an open offerable" in detail
    assert not any(r.get("id") == "#5499" for r in (doc.get("unaccepted") or []))
