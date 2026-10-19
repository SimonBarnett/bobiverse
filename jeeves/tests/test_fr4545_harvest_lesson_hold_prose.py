"""FR #4545: harvest-lesson prose 'do not merge' must not count as a PR hold."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")


LESSON_BODY = (
    "MRB (light triage): ...\n\n"
    "Lessons:\n"
    "- Harvest-lesson twin: exact title Harvest-lesson re-offer 0-behind — "
    "FAIL-supersede later tip citing first open tip; do not merge the thinner "
    "duplicate.\n"
)


def test_pr_hold_reason_ignores_do_not_merge_in_lesson_prose():
    assert (
        gitclaim.pr_hold_reason(
            title="lesson(harvest-agent-skills): Harvest-lesson twin: exact title",
            body=LESSON_BODY,
            labels=("harvest-lesson", "via-intake"),
        )
        is None
    )


def test_pr_hold_reason_still_matches_owner_on_hold_stamp():
    body = (
        "On hold (Simon 2026-10-10): this PR must not merge until FR-244 #1358 "
        "is merged. Not closing."
    )
    reason = gitclaim.pr_hold_reason(title="feat", body=body, labels=())
    assert reason
    assert "hold" in reason.lower()


def test_append_unaccepted_enqueues_harvest_lesson_with_do_not_merge_prose():
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/a-search",
        task="MRB",
        id="3627",
        event="pull_request",
        action="opened",
        line="https://github.com/SimonBarnett/a-search/pull/3627",
        title="lesson(harvest-agent-skills): Harvest-lesson twin: exact title",
        body=LESSON_BODY,
        labels=("harvest-lesson", "via-intake"),
        harvest_lesson=True,
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "added"
    assert len(doc["unaccepted"]) == 1
    assert str(doc["unaccepted"][0].get("id")) in ("3627", "#3627")


def test_enqueue_open_github_item_reports_skipped_not_duplicate_on_hold():
    doc = gitclaim._empty_queue()

    def fetch(_repo, _num):
        return {
            "number": 99,
            "state": "open",
            "draft": False,
            "title": "feat: held",
            "body": "On hold: must not merge until #1 lands.",
            "labels": [{"name": "on-hold"}],
            "html_url": "https://github.com/SimonBarnett/bobiverse/pull/99",
            "pull_request": {},
        }

    st, detail = gitclaim.enqueue_open_github_item(
        doc, "SimonBarnett/bobiverse", "MRB", "99", fetch_issue=fetch
    )
    assert st == "skipped"
    assert "already queued" not in detail
    assert "skipped" in detail.lower()
    assert doc["unaccepted"] == []
