"""FR #5500 / #6340: auto-skip docs/mrb pins; explicit !assign must still offer.

FR #5500: webhook / resync skip first-level docs/mrb while the original is open
(and pin-of-pin / harvest-lesson stay skipped). FR #6340: once a row is queued
(orphan stamp or explicit enqueue), offer must not refuse with docs_mrb_pin.
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


def test_fr5500_docs_mrb_queued_row_is_offerable():
    """FR #6340: offer path must not refuse a queued docs/mrb pin."""
    assert gitclaim.mrb_row_not_offerable_reason(_docs_mrb_row()) is None
    assert gitclaim.mrb_row_offerable(_docs_mrb_row()) is True
    assert gitclaim.mrb_row_offerable(_docs_mrb_row(docs_mrb_orphan="1")) is True


def test_fr5500_docs_mrb_head_only_queued_offerable():
    row = _docs_mrb_row(title="pin harvest skip after harvest-lesson MRB")
    assert gitclaim.is_docs_mrb_pin_pr(
        title=row["title"], head_ref=row["head"]
    )
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True


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
    """Without parent-open checker, webhook still skips (safe default)."""
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


def test_fr5500_claim_from_github_issue_docs_mrb_for_assign():
    """FR #6340 acceptance 7: explicit enqueue reaches docs/mrb pins."""
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
    claim = gitclaim.claim_from_github_issue(REPO, issue)
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.docs_mrb_orphan is True


def test_fr5500_enqueue_docs_mrb_added(tmp_path: Path):
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
    assert status == "added", (status, detail)
    rows = [r for r in (doc.get("unaccepted") or []) if r.get("id") == "#5499"]
    assert rows
    assert rows[0].get("docs_mrb_orphan") in ("1", "true", True, 1)
