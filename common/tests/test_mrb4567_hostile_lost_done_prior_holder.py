"""MRB #4567 hostile: lost-DONE prior_holder and non-PR rows."""
from __future__ import annotations

import gitclaim


def test_mrb4567_empty_prior_holder_is_not_a_reoffer():
    assert gitclaim._is_lost_done_reoffer_to({"prior_holder": ""}, "marchhare-100") is False
    assert gitclaim._is_lost_done_reoffer_to({}, "marchhare-100") is False


def test_mrb4567_prior_holder_matches_canonical_nick():
    row = {"prior_holder": "marchhare-100"}
    assert gitclaim._is_lost_done_reoffer_to(row, "marchhare-100") is True
    assert gitclaim._is_lost_done_reoffer_to(row, "marchhare-200") is False


def test_mrb4567_github_result_ignores_non_pull_rows(monkeypatch):
    called = {"n": 0}

    def boom(repo, num):
        called["n"] += 1
        raise AssertionError("must not fetch comments")

    monkeypatch.setattr("mrb_merge_gate.fetch_issue_comments", boom, raising=False)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#4564",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/4564",
    }
    assert gitclaim._lost_done_github_result(row) is None
    assert called["n"] == 0