# -*- coding: utf-8 -*-
"""FR #9885: MERGEABLE MRBs after PASS, skip draft/dirty offer, same-seat PASS block."""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"


def _mrb(num: int, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
        "mergeable": True,
        "mergeable_state": "clean",
    }
    row.update(extra)
    return row


def test_fr9885_pass_open_mergeable_stays_offerable(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = {
        "v": 1,
        "unaccepted": [_mrb(9912)],
        "accepted": [],
        "done": [_mrb(9912, result="PASS", nick="flamingo-1")],
    }

    def pr_open(repo: str, num: str) -> bool:
        return repo == REPO and str(num).lstrip("#") == "9912"

    row = doc["unaccepted"][0]
    assert gitclaim._mrb_pass_awaiting_merge(doc, row, home=tmp_path, pr_exists=pr_open)
    assert not gitclaim.mrb_already_done(doc, row, home=tmp_path, pr_exists=pr_open)
    assert gitclaim.mrb_row_offerable(row, pr_exists=pr_open)


def test_fr9885_dirty_and_draft_not_offerable():
    dirty = _mrb(9910, mergeable=False, mergeable_state="DIRTY")
    assert gitclaim.mrb_row_not_offerable_reason(dirty) == "merge-conflicting"
    assert not gitclaim.mrb_row_offerable(dirty)

    draft = _mrb(9755, draft=True)
    assert gitclaim.mrb_row_not_offerable_reason(draft) == "draft"
    assert not gitclaim.mrb_row_offerable(draft)


def test_fr9885_same_seat_blocked_after_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [_mrb(9912)],
            "accepted": [],
            "done": [_mrb(9912, result="PASS", done_by="redqueen-99")],
        },
    )
    assert gitclaim._nick_done_mrb_pass_in_doc(
        gitclaim.load_queue(tmp_path), "redqueen-99", REPO, "#9912"
    )


def test_fr9885_fail_still_already_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = {
        "v": 1,
        "unaccepted": [_mrb(42)],
        "accepted": [],
        "done": [_mrb(42, result="FAIL", nick="x-1")],
    }
    row = doc["unaccepted"][0]
    assert not gitclaim._mrb_pass_awaiting_merge(doc, row, home=tmp_path, pr_exists=None)
    assert gitclaim.mrb_already_done(doc, row, home=tmp_path, pr_exists=None)