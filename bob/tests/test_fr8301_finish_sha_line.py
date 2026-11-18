"""FR #8301: FINISH sha boilerplate is MRB/FIX only."""
from __future__ import annotations

import bob_worker as bw

WT = r"D:\jobs\bobiverse\job"
OB = r"D:\jobs\bobiverse\job\.bob\outbox.txt"


def test_fr8301_fr_and_uat_omit_mrb_board():
    fr = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#8270", worktree=WT, outbox=OB
    )
    uat = bw.opencode_job_finish_steps(
        job_key="UAT SimonBarnett/bobiverse#8270", worktree=WT, outbox=OB
    )
    for text in (fr, uat):
        assert "MRB PASS" not in text
        assert "MRB FAIL" not in text
        assert "FINISH" in text


def test_fr8301_mrb_and_fix_keep_board():
    mrb = bw.opencode_job_finish_steps(
        job_key="MRB SimonBarnett/bobiverse#8270", worktree=WT, outbox=OB
    )
    fix = bw.opencode_job_finish_steps(
        job_key="FIX SimonBarnett/bobiverse#8270", worktree=WT, outbox=OB
    )
    assert "MRB PASS" in mrb and "MRB FAIL" in mrb
    assert "MRB PASS" in fix and "MRB FAIL" in fix
