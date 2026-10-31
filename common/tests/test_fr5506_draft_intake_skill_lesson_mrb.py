"""FR #5506: draft via-intake+skill lesson PRs are offered as MRB; receipts stay skipped."""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"

LESSON_4444 = (
    "Lesson: In a git worktree, .git is a file, so Test-Path MERGE_HEAD is false.\n"
    "---\n_via-intake id=`in_6e8992840dd04b81`_\n"
)
LESSON_4967 = (
    "MRB (light triage): is the lesson useful?\n\n"
    "## Lesson\nintake.py: pure ASCII pins fail on U+2014.\n"
    "---\n_via-intake id=`in_94d9f56114b448d7`_\n"
)
RECEIPT_BODY = "Session summary:\nMRB PASS\n_via-intake Invoke-BobiverseHarvest_"
SKILL_LABS = ["via-intake", "skill"]


def _pr_opened(*, number: int, title: str, body: str, draft: bool, labels):
    return {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "draft": draft,
            "html_url": f"https://github.com/{REPO}/pull/{number}",
            "labels": [{"name": n} for n in labels],
            "head": {"ref": f"intake/in_{number}"},
        },
    }


def test_fr5506_4444_style_is_offerable_not_receipt():
    title = "worktree MERGE_HEAD: use git rev-parse not Test-Path .git/MERGE_HEAD"
    assert not gitclaim.is_intake_harvest_receipt_pr(
        title=title, body=LESSON_4444, labels=SKILL_LABS
    )
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title=title, body=LESSON_4444, labels=SKILL_LABS
    )


def test_fr5506_4967_style_is_offerable():
    title = "intake.py pure ASCII: no U+2014 em dash in docstrings"
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title=title, body=LESSON_4967, labels=SKILL_LABS
    )


def test_fr5506_receipt_still_skipped():
    title = "harvest: MRB #2642 PASS: merged PR #2642"
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=title, body=RECEIPT_BODY, labels=SKILL_LABS
    )
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title=title, body=RECEIPT_BODY, labels=SKILL_LABS
    )


def test_fr5506_webhook_draft_lesson_claims_mrb():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=4444,
            title="worktree MERGE_HEAD: use git rev-parse not Test-Path .git/MERGE_HEAD",
            body=LESSON_4444,
            draft=True,
            labels=SKILL_LABS,
        ),
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id == "#4444"


def test_fr5506_webhook_draft_receipt_still_none():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=2642,
            title="harvest: MRB #2642 PASS: merged PR #2642",
            body=RECEIPT_BODY,
            draft=True,
            labels=SKILL_LABS,
        ),
    )
    assert claim is None


def test_fr5506_claim_from_github_issue_draft_lesson():
    issue = {
        "number": 4967,
        "title": "intake.py pure ASCII: no U+2014 em dash in docstrings",
        "body": LESSON_4967,
        "state": "open",
        "html_url": f"https://github.com/{REPO}/pull/4967",
        "pull_request": {},
        "draft": True,
        "labels": [{"name": n} for n in SKILL_LABS],
    }
    claim = gitclaim.claim_from_github_issue(REPO, issue)
    assert claim is not None and claim.task == "MRB"


def test_fr5506_enqueue_draft_lesson(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)

    def fetch_issue(_repo, _num):
        return {
            "number": 4444,
            "title": "worktree MERGE_HEAD: use git rev-parse not Test-Path .git/MERGE_HEAD",
            "body": LESSON_4444,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/4444",
            "pull_request": {},
            "draft": True,
            "labels": [{"name": n} for n in SKILL_LABS],
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "4444", fetch_issue=fetch_issue, home=home
    )
    assert status == "added", detail
    assert any(r.get("id") == "#4444" for r in (doc.get("unaccepted") or []))
