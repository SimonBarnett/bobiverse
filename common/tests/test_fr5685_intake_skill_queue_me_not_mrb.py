"""FR #5685: via-intake+skill queue-me / no-Lesson stubs must not become MRB."""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/agentic_fomprep"
SKILL_LABS = ["via-intake", "skill"]

# agentic_fomprep#144 shape: status stub + intake footer, only docs/intake-harvest/*.
FOM_144_TITLE = "fr004 offline"
FOM_144_BODY = (
    "queue me\n"
    "---\n"
    "_via-intake id=`in_75bd945dfaa64ccc` ts=`2026-10-08T22:17:00Z`_\n"
    "_source machine=`marchhare` agent=`Report-FomprepIntakeIssue` "
    "book=`harvest-priority-skills` ver=`-`_\n"
)

# FR #5506 real lesson shapes must stay offerable.
LESSON_4444 = (
    "Lesson: In a git worktree, .git is a file, so Test-Path MERGE_HEAD is false.\n"
    "---\n_via-intake id=`in_6e8992840dd04b81`_\n"
)
LESSON_4967 = (
    "MRB (light triage): is the lesson useful?\n\n"
    "## Lesson\nintake.py: pure ASCII pins fail on U+2014.\n"
    "---\n_via-intake id=`in_94d9f56114b448d7`_\n"
)


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


def test_fr5685_fomprep144_is_receipt_not_offerable():
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=FOM_144_TITLE, body=FOM_144_BODY, labels=SKILL_LABS
    )
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title=FOM_144_TITLE, body=FOM_144_BODY, labels=SKILL_LABS
    )


def test_fr5685_title_alone_without_lesson_body_not_offerable():
    """Fallthrough on non-harvest title must not offer stubs (FR #5685)."""
    body = "---\n_via-intake id=`in_deadbeef`_\n"
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title="some skill tip without lesson section",
        body=body,
        labels=SKILL_LABS,
    )
    assert gitclaim.is_intake_harvest_receipt_pr(
        title="some skill tip without lesson section",
        body=body,
        labels=SKILL_LABS,
    )


def test_fr5685_real_lesson_shapes_still_offerable():
    title = "worktree MERGE_HEAD: use git rev-parse not Test-Path .git/MERGE_HEAD"
    assert not gitclaim.is_intake_harvest_receipt_pr(
        title=title, body=LESSON_4444, labels=SKILL_LABS
    )
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title=title, body=LESSON_4444, labels=SKILL_LABS
    )
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title="intake.py pure ASCII: no U+2014 em dash in docstrings",
        body=LESSON_4967,
        labels=SKILL_LABS,
    )


def test_fr5685_webhook_draft_queue_me_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=144,
            title=FOM_144_TITLE,
            body=FOM_144_BODY,
            draft=True,
            labels=SKILL_LABS,
        ),
    )
    assert claim is None


def test_fr5685_webhook_ready_queue_me_produces_no_claim():
    """Non-draft stubs must also skip (receipt path), not only draft offerable gate."""
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=144,
            title=FOM_144_TITLE,
            body=FOM_144_BODY,
            draft=False,
            labels=SKILL_LABS,
        ),
    )
    assert claim is None


def test_fr5685_resync_skips_queue_me_draft(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)

    def fetch_issue(_repo, _num):
        return {
            "number": 144,
            "title": FOM_144_TITLE,
            "body": FOM_144_BODY,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/144",
            "pull_request": {},
            "draft": True,
            "labels": [{"name": n} for n in SKILL_LABS],
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "144", fetch_issue=fetch_issue, home=home
    )
    assert status != "added", detail
    assert not any(r.get("id") == "#144" for r in (doc.get("unaccepted") or []))
