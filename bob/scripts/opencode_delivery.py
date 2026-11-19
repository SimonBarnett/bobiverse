"""FR #8283: OpenCode close-steps loaded from disk on each finish.

A long-running worker keeps bob_worker.py in memory. Finish prompts call
this module and reload it when the file changes, so an MRB prompt cannot
stay on the pre-FR-#8248 "commit on fr-N / gh pr create" text after the
file on disk has moved.
"""
from __future__ import annotations

import re


def job_task_kind(job_key: str) -> str:
    """FR, MRB, UAT, or FIX from the job key. Empty when unknown."""
    m = re.match(r"(?i)^\s*(FR|MRB|UAT|FIX)\b", job_key or "")
    return m.group(1).upper() if m else ""


def opencode_typed_delivery(
    job_key: str,
    *,
    branch: str = "",
    closes_ref: str = "",
    outbox: str = "",
    pr_state: str = "",
    head_ref: str = "",
) -> str:
    """Finish/retry/corrective close steps for this task type only."""
    key = (job_key or "job").strip() or "job"
    kind = job_task_kind(key)
    ref = (closes_ref or "").strip()
    if not ref:
        ref = re.sub(r"(?i)^\s*(?:FR|MRB|UAT|FIX)\s+", "", key).strip() or key
    ob = (outbox or "$env:BOB_OUTBOX").strip()
    if kind == "MRB" and str(pr_state or "").upper() == "MERGED":
        # FR #8307: a re-offered or already-merged MRB must not be given FR steps
        # (commit on fr-<issue>, git push, gh pr create).
        return (
            "This MRB pull request is already MERGED. "
            "Re-verify the merge commit, that Closes closed the issue, and that the MRB board is posted. "
            "Do not commit. Do not git push. Do not open a pull request. "
            "Do not use a branch named from this issue number. "
            f"Append DONE MRB {ref} PASS and the existing pull request URL to $env:BOB_OUTBOX ({ob})."
        )
    if kind == "MRB":
        head = (head_ref or "").strip()
        head_bit = (
            f"The pull request head branch is {head}. "
            if head
            else "Use gh pr view headRefName for the pull request head branch. "
        )
        return (
            "This job is an MRB. Post MRB PASS or MRB FAIL on the pull request at the reviewed HEAD sha. "
            "On FAIL, open one separate fix pull request for the defect. "
            + head_bit
            + "Do not commit the review onto a branch named from this issue number. "
            "Do not open a pull request that implements this MRB. "
            "Do not push commits onto the pull request under review. "
            f"Append DONE MRB {ref} PASS or FAIL and the pull request URL to $env:BOB_OUTBOX ({ob})."
        )
    if kind == "FIX":
        return (
            "This job is a FIX. Commit on the pull request head branch already checked out. "
            "git push origin HEAD. Do not open a new pull request. "
            f"Append DONE FIX {ref} and the existing pull request URL to $env:BOB_OUTBOX ({ob})."
        )
    br = (branch or "").strip()
    if not br:
        num = re.search(r"(?i)#(\d+)\s*$", key)
        br = f"fr-{num.group(1)}" if num else "the feature branch for this issue"
    return (
        f"Commit on branch {br}. git push -u origin HEAD. "
        f"Open the PR with gh pr create --base main --body \"Closes {ref}\" "
        "(or --body-file pointing at a markdown file inside this worktree, e.g. .bob/pr-body.md). "
        "If gh issue view shows the issue CLOSED, do not run gh pr create. "
        "Set the PR ready for review before DONE, never leave it draft: run gh pr ready. "
        f"Immediately append DONE for {key} with the PR URL to $env:BOB_OUTBOX ({ob}) "
        "right after gh pr create returns the URL."
    )
