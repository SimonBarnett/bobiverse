"""FR #9080: done-fix / head-move MRB requeue must refresh labels; hold skips dirty-FIX.

Class of bobiverse#8757: ensure_mrb_requeued_after_head_move stamped
title=\"requeue after done-fix\" with labels=() so pr_hold_reason / mrb_row_offerable
missed GitHub ``hold``. Dirty-FIX resync offered the held tip.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import mrb_merge_on_green


REPO = "SimonBarnett/bobiverse"
PR = "#8757"
URL = f"https://github.com/{REPO}/pull/8757"


def test_ensure_mrb_requeue_skips_when_snapshot_has_hold_label(tmp_path: Path):
    doc = gitclaim._empty_queue()
    st = gitclaim.ensure_mrb_requeued_after_head_move(
        doc,
        tmp_path,
        repo=REPO,
        pr=PR,
        url=URL,
        reason="done-fix",
        pr_snapshot={
            "title": "lesson(harvest): BOB-05 models docs",
            "body": "Closes SimonBarnett/bobiverse#8702",
            "labels": ["via-intake", "harvest-lesson", "hold"],
        },
        fetch_pr=False,
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []


def test_ensure_mrb_requeue_preserves_prior_row_labels_and_real_title(tmp_path: Path):
    doc = gitclaim._empty_queue()
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": PR,
            "title": "lesson(harvest): real tip title",
            "body": "Closes SimonBarnett/bobiverse#8702",
            "labels": ["via-intake", "harvest-lesson"],
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
    )
    assert st == "duplicate"
    row = doc["unaccepted"][0]
    assert row.get("title") == "lesson(harvest): real tip title"
    assert "hold" not in {str(x).lower() for x in (row.get("labels") or [])}
    assert "harvest-lesson" in {str(x).lower() for x in (row.get("labels") or [])}
    assert not str(row.get("title") or "").startswith("requeue after")


def test_ensure_mrb_requeue_prior_hold_labels_purge(tmp_path: Path):
    doc = gitclaim._empty_queue()
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": PR,
            "title": "lesson(harvest): held tip",
            "body": "",
            "labels": ["hold", "harvest-lesson"],
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
    )
    assert st == "skipped"
    assert doc["unaccepted"] == []


def test_append_unaccepted_mrb_hold_purges_existing(tmp_path: Path):
    doc = gitclaim._empty_queue()
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": "#8757",
            "title": "old",
            "labels": [],
            "url": URL,
            "line": URL,
        }
    ]
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#8757",
        event="pull_request",
        action="synchronize",
        line=URL,
        title="lesson tip",
        body="",
        labels=("hold",),
    )
    assert gitclaim._append_unaccepted(doc, claim, url=URL) == "skipped"
    assert doc["unaccepted"] == []


def test_offer_dirty_conflict_fix_skips_when_pr_held(tmp_path: Path, monkeypatch):
    home = tmp_path

    def _snap(repo: str, pr: str, token: str | None = None):
        return {
            "title": "lesson(harvest): held dirty tip",
            "body": "Closes SimonBarnett/bobiverse#8702",
            "labels": ["hold", "harvest-lesson"],
            "sha": "abc123",
            "closed": False,
            "merged": False,
        }

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", _snap)
    result = mrb_merge_on_green.offer_dirty_conflict_fix(
        home,
        repo=REPO,
        pr="8757",
        sha="abc123def456",
        url=URL,
        reason="dirty",
    )
    assert result == "skipped"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert fixes == []


def test_linked_issue_hold_blocks_dirty_fix(tmp_path: Path, monkeypatch):
    home = tmp_path

    def _snap(repo: str, pr: str, token: str | None = None):
        return {
            "title": "FR #8702 docs",
            "body": "Closes SimonBarnett/bobiverse#8702",
            "labels": ["via-intake"],  # no PR hold (issues-only policy)
            "sha": "abc123",
            "closed": False,
            "merged": False,
        }

    def _issue(repo: str, ident: str):
        assert ident in ("#8702", "8702")
        return {
            "title": "BOB-05 models docs",
            "body": "HOLD: phase-gated. Do not start.",
            "labels": ["hold", "feature-request"],
            "state": "open",
        }

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", _snap)
    result = mrb_merge_on_green.offer_dirty_conflict_fix(
        home,
        repo=REPO,
        pr="8757",
        sha="abc123def456",
        url=URL,
        reason="dirty",
        issue_lookup=_issue,
    )
    assert result == "skipped"


def test_linked_issue_hold_reason_from_closes_body():
    def _issue(repo: str, ident: str):
        return {"title": "x", "body": "", "labels": ["hold"], "state": "open"}

    why = gitclaim.linked_issue_hold_reason(
        REPO,
        body="Closes SimonBarnett/bobiverse#8702\n",
        issue_lookup=_issue,
    )
    assert why is not None
    assert "8702" in why or "hold" in why.lower()
