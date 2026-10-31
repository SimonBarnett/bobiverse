"""docs/mrb-5507: pin FR #5506 / PR #5507 draft via-intake+skill MRB offer.

Ordinary drafts stay skipped (FR #2604). Receipt footers stay skipped (FR #2650).
"""
from __future__ import annotations

import gitclaim

REPO = "SimonBarnett/bobiverse"


def _opened(*, number: int, title: str, body: str, draft: bool, labels):
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
            "head": {"ref": "fr-example"},
        },
    }


def test_mrb5507_ordinary_draft_product_pr_still_skipped():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _opened(
            number=5507,
            title="FR #5506: offer draft intake skill lessons as MRB",
            body="Closes SimonBarnett/bobiverse#5506",
            draft=True,
            labels=[],
        ),
    )
    assert claim is None


def test_mrb5507_offerable_requires_via_intake_and_skill():
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title="worktree MERGE_HEAD: use git rev-parse",
        body="Lesson: use rev-parse\n",
        labels=("via-intake",),
    )
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title="worktree MERGE_HEAD: use git rev-parse",
        body="Lesson: use rev-parse\n",
        labels=("via-intake", "skill"),
    )
