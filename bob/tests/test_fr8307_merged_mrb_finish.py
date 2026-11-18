"""FR #8307: an already-merged MRB FINISH must not list FR commit/push/pr-create steps."""
from __future__ import annotations

import bob_worker as bw

WT = r"D:\jobs\bobiverse\mrb-8280"
OB = r"D:\jobs\bobiverse\mrb-8280\.bob\outbox.txt"
KEY = "MRB SimonBarnett/bobiverse#8280"


def test_fr8307_merged_mrb_skips_fr_steps(monkeypatch):
    def fake_finish(job_key, directory="", *, run=None):
        return "e7f60b5d7aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "gh-headRefOid", "MERGED"

    monkeypatch.setattr("opencode_seat_contract.finish_reviewed_sha", fake_finish)
    text = bw.opencode_job_finish_steps(job_key=KEY, worktree=WT, outbox=OB)
    assert "already MERGED" in text
    assert "Re-verify the merge commit" in text
    assert "gh pr create" not in text
    assert "commit on branch" not in text.lower()
    assert "fr-8280" not in text
    assert "DONE MRB SimonBarnett/bobiverse#8280 PASS" in text


def test_fr8307_open_mrb_still_has_no_pr_create():
    text = bw.opencode_typed_delivery(KEY, closes_ref="SimonBarnett/bobiverse#8280", outbox=OB)
    assert "gh pr create" not in text
    assert "headRefName" in text
    assert "one separate fix pull request" in text
