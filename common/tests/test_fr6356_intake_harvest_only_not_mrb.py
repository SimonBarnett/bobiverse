"""FR #6356: draft docs/intake-harvest-only tips must not become MRB.

agentic_fomprep#377: via-intake+skill draft with LESSON_PR_MRB_INSTRUCTION
boilerplate (MRB light triage) but only docs/intake-harvest/*.md and no
``Lesson`` / ``## Lesson`` section was offered as MRB. Receipts stay skipped;
real Lesson bodies stay offerable (FR #5506 / #5685).
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake

REPO = "SimonBarnett/agentic_fomprep"
SKILL_LABS = ["via-intake", "skill"]

# Live shape of agentic_fomprep#377 (CLOSED as receipt by redqueen-5868).
FOM_377_TITLE = "Never dump customer connections files even for redaction"
FOM_377_BODY = (
    f"{intake.LESSON_PR_MRB_INSTRUCTION}\n\n"
    "Failure: a PowerShell pass over hillier-connections.txt intended to print "
    "only keys leaked PASSWORD values into the agent tool log.\n"
    "Rule: never Get-Content / write connections files to stdout.\n"
    "---\n"
    "_via-intake id=`in_229c5131ab054796` ts=`2026-11-09T21:45:27Z`_\n"
    "_source machine=`marchhare` agent=`Report-FomprepIntakeIssue` "
    "book=`harvest-agent-skills` ver=`-`_\n"
)
FOM_377_FILES = ["docs/intake-harvest/intake-in_229c5131ab054796.md"]

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


def test_fr6356_fomprep377_light_triage_boilerplate_is_receipt():
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=FOM_377_TITLE, body=FOM_377_BODY, labels=SKILL_LABS
    )
    assert not gitclaim.is_offerable_intake_skill_lesson_pr(
        title=FOM_377_TITLE, body=FOM_377_BODY, labels=SKILL_LABS
    )


def test_fr6356_intake_harvest_only_paths_are_receipt():
    assert gitclaim.is_intake_harvest_only_paths(FOM_377_FILES)
    assert gitclaim.is_intake_harvest_receipt_pr(
        title=FOM_377_TITLE,
        body=FOM_377_BODY,
        labels=SKILL_LABS,
        files=FOM_377_FILES,
    )
    assert not gitclaim.is_intake_harvest_only_paths(
        ["docs/intake-harvest/x.md", ".grok/skills/harvest/SKILL.md"]
    )
    assert not gitclaim.is_intake_harvest_only_paths([])


def test_fr6356_real_lesson_shapes_still_offerable():
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


def test_fr6356_webhook_draft_377_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=377,
            title=FOM_377_TITLE,
            body=FOM_377_BODY,
            draft=True,
            labels=SKILL_LABS,
        ),
    )
    assert claim is None


def test_fr6356_webhook_ready_377_still_no_claim():
    """Non-draft intake-harvest receipts must also skip (receipt path)."""
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened(
            number=377,
            title=FOM_377_TITLE,
            body=FOM_377_BODY,
            draft=False,
            labels=SKILL_LABS,
        ),
    )
    assert claim is None


def test_fr6356_claim_from_github_issue_draft_377_none():
    issue = {
        "number": 377,
        "title": FOM_377_TITLE,
        "body": FOM_377_BODY,
        "state": "open",
        "draft": True,
        "pull_request": {},
        "html_url": f"https://github.com/{REPO}/pull/377",
        "labels": [{"name": n} for n in SKILL_LABS],
    }
    assert gitclaim.claim_from_github_issue(REPO, issue) is None


def test_fr6356_enqueue_draft_377_skipped(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    doc = gitclaim.load_queue(home)

    def fetch_issue(_repo, _num):
        return {
            "number": 377,
            "title": FOM_377_TITLE,
            "body": FOM_377_BODY,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/377",
            "pull_request": {},
            "draft": True,
            "labels": [{"name": n} for n in SKILL_LABS],
            "changed_files": FOM_377_FILES,
        }

    status, detail = gitclaim.enqueue_open_github_item(
        doc, REPO, "MRB", "377", fetch_issue=fetch_issue, home=home
    )
    assert status != "added", detail
    assert not any(r.get("id") == "#377" for r in (doc.get("unaccepted") or []))
