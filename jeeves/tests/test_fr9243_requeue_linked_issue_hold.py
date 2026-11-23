"""FR #9243: ensure_mrb_requeued_after_head_move must honour linked_issue_hold_reason.

Docstring claimed linked holds block head-move MRB requeue, but only
pr_hold_reason ran. Dirty-FIX already checks linked holds via injectable
issue_lookup; head-move must match (no network when lookup is omitted /
under queue lock).
"""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"
PR = "#8757"
URL = f"https://github.com/{REPO}/pull/8757"
BODY = "Closes SimonBarnett/bobiverse#8702\n"


def test_fr9243_linked_hold_label_skips_requeue(tmp_path: Path):
    """Linked issue ``hold`` label alone skips head-move requeue."""

    def _issue(repo: str, ident: str):
        assert ident in ("#8702", "8702")
        return {
            "title": "gated FR",
            "body": "phase work",
            "labels": ["hold", "feature-request"],
            "state": "open",
        }

    doc = gitclaim._empty_queue()
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        pr_snapshot={
            "title": "FR tip",
            "body": BODY,
            "labels": ["via-intake"],  # no PR hold (FR #9082 issues-only)
        },
        fetch_pr=False,
        issue_lookup=_issue,
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []


def test_fr9243_linked_hold_body_stamp_skips_requeue(tmp_path: Path):
    """Linked issue HOLD: body stamp alone skips (no hold label on issue)."""

    def _issue(repo: str, ident: str):
        return {
            "title": "gated FR",
            "body": "HOLD: phase-gated. Do not start.\n",
            "labels": ["feature-request"],
            "state": "open",
        }

    doc = gitclaim._empty_queue()
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="synchronize",
        pr_snapshot={
            "title": "FR tip",
            "body": BODY,
            "labels": ["via-intake"],
        },
        fetch_pr=False,
        issue_lookup=_issue,
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []


def test_fr9243_linked_hold_purges_existing_unaccepted(tmp_path: Path):
    def _issue(repo: str, ident: str):
        return {"title": "x", "body": "", "labels": ["on-hold"], "state": "open"}

    doc = gitclaim._empty_queue()
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": PR,
            "title": "prior",
            "body": BODY,
            "labels": ["via-intake"],
            "url": URL,
            "line": URL,
        }
    ]
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        fetch_pr=False,
        issue_lookup=_issue,
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []


def test_fr9243_linked_hold_leaves_accepted_mrb(tmp_path: Path):
    """Accepted MRB stays; only unaccepted twin is purged (seat already owns it)."""

    def _issue(repo: str, ident: str):
        return {"title": "x", "body": "", "labels": ["hold"], "state": "open"}

    doc = gitclaim._empty_queue()
    accepted = {
        "repo": REPO,
        "task": "MRB",
        "id": PR,
        "title": "in flight",
        "body": BODY,
        "labels": ["via-intake"],
        "url": URL,
        "line": URL,
        "accepted_by": "flamingo-1",
    }
    doc["accepted"] = [accepted]
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": PR,
            "title": "twin",
            "body": BODY,
            "labels": [],
            "url": URL,
            "line": URL,
        }
    ]
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        fetch_pr=False,
        issue_lookup=_issue,
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []
    assert len(doc["accepted"]) == 1
    assert doc["accepted"][0]["accepted_by"] == "flamingo-1"


def test_fr9243_no_lookup_skips_network_and_allows_requeue(tmp_path: Path):
    """issue_lookup=None: no linked check (lock-safe); requeue proceeds."""
    calls: list[tuple[str, str]] = []

    def _boom(repo: str, ident: str):
        calls.append((repo, ident))
        raise AssertionError("must not be called when issue_lookup omitted")

    doc = gitclaim._empty_queue()
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        pr_snapshot={
            "title": "FR tip",
            "body": BODY,
            "labels": ["via-intake"],
        },
        fetch_pr=False,
        # omit issue_lookup — must not invent a default network fetch
    )
    assert st == "added"
    assert len(doc["unaccepted"]) == 1
    assert calls == []
    # Prove _boom would have been reachable if wrongly defaulted:
    st2 = gitclaim.ensure_mrb_requeued_after_head_move(
        gitclaim._empty_queue(),
        tmp_path,
        repo=REPO,
        pr="#99",
        url=f"https://github.com/{REPO}/pull/99",
        reason="done-fix",
        pr_snapshot={"title": "t", "body": BODY, "labels": []},
        fetch_pr=False,
        issue_lookup=_boom,
    )
    # Lookup raises → linked_issue_hold_reason continues → requeue added
    assert st2 == "added"
    assert calls  # was invoked when explicitly passed


def test_fr9243_clear_linked_issue_allows_requeue(tmp_path: Path):
    def _issue(repo: str, ident: str):
        return {
            "title": "ready",
            "body": "go",
            "labels": ["feature-request"],
            "state": "open",
        }

    doc = gitclaim._empty_queue()
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        pr_snapshot={"title": "FR tip", "body": BODY, "labels": ["via-intake"]},
        fetch_pr=False,
        issue_lookup=_issue,
    )
    assert st == "added"
    assert len(doc["unaccepted"]) == 1


def test_fr9243_source_pins_issue_lookup_param():
    import inspect

    src = inspect.getsource(gitclaim.ensure_mrb_requeued_after_head_move)
    assert "issue_lookup" in src
    assert "linked_issue_hold_reason" in src
    assert "FR #9243" in src or "9243" in src
