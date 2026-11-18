"""FR #8248: finish, retry, and corrective prompts follow the job task type."""
from __future__ import annotations

import re

import bob_worker as bw

FR = "FR SimonBarnett/bobiverse#6360"
MRB = "MRB SimonBarnett/bobiverse#8224"
FIX = "FIX SimonBarnett/bobiverse#8224"
WT = r"D:\jobs\bobiverse\job"
OB = r"D:\jobs\bobiverse\job\.bob\outbox.txt"


def test_fr8248_finish_and_retry_match_task_type():
    fr = bw.opencode_job_finish_steps(job_key=FR, worktree=WT, outbox=OB)
    mrb = bw.opencode_job_finish_steps(job_key=MRB, worktree=WT, outbox=OB)
    fix = bw.opencode_job_finish_steps(job_key=FIX, worktree=WT, outbox=OB)
    assert "fr-6360" in fr
    assert "gh pr create" in fr
    assert "DONE" in fr
    assert re.search(r"fr-\d+", mrb) is None
    assert "gh pr create" not in mrb
    assert "MRB PASS" in mrb and "MRB FAIL" in mrb
    assert "one separate fix pull request" in mrb
    assert "push origin HEAD" in fix
    assert "Do not open a new pull request" in fix
    assert "gh pr create" not in fix
    retry = bw.opencode_done_miss_reminder_line(
        shop="#flamingo", outbox=OB, job_key=MRB, worktree=WT
    )
    assert re.search(r"fr-\d+", retry) is None
    assert "MRB PASS" in retry


def test_fr8283_mrb_finish_reloads_without_feature_branch():
    """A served MRB FINISH must not say commit on fr-8263 or gh pr create."""
    text = bw.opencode_job_finish_steps(
        job_key="MRB SimonBarnett/bobiverse#8263", worktree=WT, outbox=OB
    )
    assert re.search(r"fr-\d+", text) is None
    assert "gh pr create" not in text
    assert "one separate fix pull request" in text
    assert "DONE MRB SimonBarnett/bobiverse#8263" in text


def test_fr8248_corrective_matches_task_type():
    mrb = bw.opencode_external_dir_corrective_steps(
        job_key=MRB, worktree=WT, outbox=OB, scratch=WT + r"\.bob\tmp"
    )
    fr = bw.opencode_external_dir_corrective_steps(
        job_key=FR, worktree=WT, outbox=OB, scratch=WT + r"\.bob\tmp"
    )
    assert "external_directory" in mrb
    assert re.search(r"fr-\d+", mrb) is None
    assert "MRB PASS" in mrb
    assert "DONE MRB SimonBarnett/bobiverse#8224" in mrb
    assert "DONE MRB MRB " not in mrb
    assert "fr-6360" in fr
    assert "gh pr create" in fr
    assert "Closes SimonBarnett/bobiverse#6360" in fr
    assert "Closes FR " not in fr
    fix = bw.opencode_external_dir_corrective_steps(
        job_key=FIX, worktree=WT, outbox=OB, scratch=WT + r"\.bob\tmp"
    )
    assert "DONE FIX SimonBarnett/bobiverse#8224" in fix
    assert "DONE FIX FIX " not in fix
