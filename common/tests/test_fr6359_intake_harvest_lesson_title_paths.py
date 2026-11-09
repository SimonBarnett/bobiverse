"""FR #6359: intake-harvest-only tips stay receipts even with lesson( title + ## Lesson.

bobiverse#6358: via-intake+skill draft titled lesson(gitclaim):..., body with ## Lesson,
files only docs/intake-harvest/*.md was offered as MRB after FR #6356. The lesson(
title exemption ran before the path filter, so files= never applied.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake

REPO = "SimonBarnett/bobiverse"
SKILL_LABS = ["via-intake", "skill"]

# Live shape of bobiverse#6358 (CLOSED not-useful by redqueen-8968).
TIP_6358_TITLE = (
    "lesson(gitclaim): via-intake+skill drafts need real Lesson section "
    "(not light-triage boilerplate)"
)
TIP_6358_BODY = (
    f"{intake.LESSON_PR_MRB_INSTRUCTION}\n\n"
    "Playbook from MRB #6357 / FR #6356 (merged PR #6357).\n\n"
    "## Lesson\n"
    "Chair ``is_offerable_intake_skill_lesson_pr`` must require a real "
    "``Lesson`` / ``## Lesson`` body section.\n"
    "---\n"
    "_via-intake id=`in_565705719e3246e0` ts=`2026-11-09T22:09:40Z`_\n"
    "_source machine=`flamingo` agent=`Report-BobiverseIntakeIssue` "
    "book=`harvest` ver=`-`_\n"
)
TIP_6358_FILES = ["docs/intake-harvest/intake-in_565705719e3246e0.md"]
REAL_SKILL_FILES = [
    "docs/intake-harvest/intake-in_x.md",
    ".grok/skills/harvest-agent-skills/SKILL.md",
]


def _pr_opened(*, number: int, title: str, body: str, draft: bool, labels, files=None):
    pr = {
        "number": number,
        "title": title,
        "body": body,
        "draft": draft,
        "html_url": f"https://github.com/{REPO}/pull/{number}",
        "labels": [{"name": n} for n in labels],
        "head": {"ref": f"intake/in_{number}"},
    }
    if files is not None:
        pr["changed_files"] = list(files)
    return {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": pr,
    }


def test_fr6359_lesson_title_intake_harvest_only_is_receipt():
    """#6358 shape with known files must not be offerable."""
    assert gitclaim.is_intake_harvest_only_paths(TIP_6358_FILES)
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=SKILL_LABS,
        files=TIP_6358_FILES,
    )
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=SKILL_LABS,
        files=TIP_6358_FILES,
    )


def test_fr6359_harvest_lesson_label_intake_harvest_only_is_receipt():
    labs = ["via-intake", "skill", "harvest-lesson"]
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=labs,
        files=TIP_6358_FILES,
    )
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=labs,
        files=TIP_6358_FILES,
    )


def test_fr6359_real_skill_book_paths_still_offerable():
    assert not gitclaim.is_intake_harvest_only_paths(REAL_SKILL_FILES)
    assert not gitclaim.is_intake_harvest_receipt_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=SKILL_LABS,
        files=REAL_SKILL_FILES,
    )
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title=TIP_6358_TITLE,
        body=TIP_6358_BODY,
        labels=SKILL_LABS,
        files=REAL_SKILL_FILES,
    )


def test_fr6359_webhook_6358_with_files_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=6358,
            title=TIP_6358_TITLE,
            body=TIP_6358_BODY,
            draft=True,
            labels=SKILL_LABS,
            files=TIP_6358_FILES,
        ),
    )
    assert claim is None


def test_fr6359_webhook_fetches_files_when_missing(monkeypatch):
    """Webhook payloads often omit file lists; fetch before classifying (FR #6359)."""
    calls = []

    def fake_fetch(repo: str, num: int, *, fetch_json=None):
        calls.append((repo, num))
        return list(TIP_6358_FILES)

    monkeypatch.setattr(gitclaim, "fetch_pr_changed_paths", fake_fetch)
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=6358,
            title=TIP_6358_TITLE,
            body=TIP_6358_BODY,
            draft=True,
            labels=SKILL_LABS,
            files=None,
        ),
    )
    assert claim is None
    assert len(calls) == 1
    assert calls[0][0] == REPO
    assert int(str(calls[0][1]).lstrip("#")) == 6358


def test_fr6359_claim_from_github_issue_fetches_files(monkeypatch):
    monkeypatch.setattr(
        gitclaim,
        "fetch_pr_changed_paths",
        lambda repo, num, *, fetch_json=None: list(TIP_6358_FILES),
    )
    issue = {
        "number": 6358,
        "title": TIP_6358_TITLE,
        "body": TIP_6358_BODY,
        "state": "open",
        "draft": True,
        "pull_request": {},
        "html_url": f"https://github.com/{REPO}/pull/6358",
        "labels": [{"name": n} for n in SKILL_LABS],
    }
    assert gitclaim.claim_from_github_issue(REPO, issue) is None


def test_fr6359_enqueue_6358_skipped_with_files(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)

    def fetch_issue(_repo, _num):
        return {
            "number": 6358,
            "title": TIP_6358_TITLE,
            "body": TIP_6358_BODY,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/6358",
            "pull_request": {},
            "draft": True,
            "labels": [{"name": n} for n in SKILL_LABS],
            "changed_files": TIP_6358_FILES,
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "6358", fetch_issue=fetch_issue, home=home
    )
    assert status != "added", detail
    assert not any(r.get("id") == "#6358" for r in (doc.get("unaccepted") or []))
