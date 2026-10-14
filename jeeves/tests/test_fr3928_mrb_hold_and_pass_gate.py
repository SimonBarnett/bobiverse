"""FR #3928: owner hold blocks MRB offer; merge requires posted MRB PASS board."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")
mrb_merge_gate = importlib.import_module("mrb_merge_gate")


def test_pr_hold_reason_from_on_hold_comment_text():
    body = (
        "On hold (Simon 2026-10-10): this PR must not merge until FR-244 #1358 "
        "is merged. Not closing."
    )
    reason = gitclaim.pr_hold_reason(title="", body=body, labels=())
    assert reason
    assert "hold" in reason.lower() or "merge" in reason.lower()


def test_pr_hold_reason_from_label():
    assert gitclaim.pr_hold_reason(title="feat", body="", labels=("on-hold",))
    assert gitclaim.pr_hold_reason(title="feat", body="", labels=("do-not-merge",))
    assert gitclaim.pr_hold_reason(title="feat", body="", labels=()) is None


def test_pr_hold_reason_ignores_unrelated_body():
    assert (
        gitclaim.pr_hold_reason(
            title="enable etsy",
            body="Keep-both with skimlinks. Floors 20.",
            labels=(),
        )
        is None
    )


def test_mrb_row_offerable_false_when_hold_label_or_body():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "1334",
        "url": "https://github.com/SimonBarnett/a-search/pull/1334",
        "labels": ["on-hold"],
    }
    assert gitclaim.mrb_row_offerable(row) is False

    row2 = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "1334",
        "url": "https://github.com/SimonBarnett/a-search/pull/1334",
        "body": "On hold: must not merge until #1358 lands.",
    }
    assert gitclaim.mrb_row_offerable(row2) is False


def test_mrb_row_offerable_true_without_hold():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "1334",
        "url": "https://github.com/SimonBarnett/a-search/pull/1334",
        "title": "FR-170 enable etsy",
        "body": "Closes SimonBarnett/a-search#1017",
        "labels": [],
    }
    assert gitclaim.mrb_row_offerable(row) is True


def test_append_unaccepted_skips_mrb_when_hold(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    doc = gitclaim._empty_queue()
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/a-search",
        task="MRB",
        id="1334",
        event="pull_request",
        action="opened",
        line="https://github.com/SimonBarnett/a-search/pull/1334",
        title="FR-170 enable etsy",
        body="On hold (Simon): must not merge until FR-244 #1358 merges.",
        labels=("on-hold",),
    )
    changed = gitclaim._append_unaccepted(doc, claim, url=claim.line)
    assert changed == "skipped"
    assert doc["unaccepted"] == []


def test_merge_gate_detects_owner_hold_comment():
    comments = [
        {
            "user": {"login": "SimonBarnett"},
            "author_association": "OWNER",
            "body": "On hold: this PR must not merge until #1358 is merged.",
            "created_at": "2026-10-10T13:53:22Z",
        }
    ]
    hold = mrb_merge_gate.find_active_owner_hold(comments)
    assert hold is not None
    assert "must not merge" in hold.lower() or "on hold" in hold.lower()


def test_fr4041_mrb_board_discussing_hold_is_not_owner_hold():
    """OWNER-posted ## MRB board that mentions hold labels must not refuse merge."""
    board = (
        "## MRB board\n\n"
        "**Verdict:** PASS\n\n"
        "**Drift:** ACCEPTABLE — hold labels / on-hold / do-not-merge discussed; "
        "product FR hold skip lands. Must not merge wording only in findings prose.\n"
        "Hostile: hold label gate covered.\n"
    )
    comments = [
        {
            "user": {"login": "SimonBarnett"},
            "author_association": "OWNER",
            "body": board,
            "created_at": "2026-10-11T14:40:00Z",
        }
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is None
    ok, reason = mrb_merge_gate.evaluate_merge_gate(comments)
    assert ok is True
    assert reason == ""


def test_merge_gate_hold_cleared_by_later_owner_comment():
    comments = [
        {
            "user": {"login": "SimonBarnett"},
            "author_association": "OWNER",
            "body": "On hold: must not merge until #1358.",
            "created_at": "2026-10-10T13:53:22Z",
        },
        {
            "user": {"login": "SimonBarnett"},
            "author_association": "OWNER",
            "body": "Hold lifted — ok to merge after FR-244 landed.",
            "created_at": "2026-10-11T12:00:00Z",
        },
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is None


def test_merge_gate_requires_mrb_pass_board():
    comments = [
        {
            "user": {"login": "win-mpre8vi4u6u-15220"},
            "author_association": "NONE",
            "body": "pushed keep-both",
            "created_at": "2026-10-11T01:19:00Z",
        }
    ]
    assert mrb_merge_gate.find_mrb_pass_board(comments) is None

    comments.append(
        {
            "user": {"login": "win-mpre8vi4u6u-15220"},
            "author_association": "NONE",
            "body": "## MRB board — #1334 PASS\n\n**Verdict:** PASS\n**Drift:** ACCEPTABLE",
            "created_at": "2026-10-11T02:30:08Z",
        }
    )
    assert mrb_merge_gate.find_mrb_pass_board(comments) is not None


def test_check_mrb_merge_allowed_blocks_without_pass_or_with_hold():
    hold_only = [
        {
            "user": {"login": "SimonBarnett"},
            "author_association": "OWNER",
            "body": "On hold: must not merge until #1358.",
            "created_at": "2026-10-10T13:53:22Z",
        }
    ]
    ok, reason = mrb_merge_gate.evaluate_merge_gate(hold_only)
    assert ok is False
    assert "hold" in reason.lower()

    no_board = [
        {
            "user": {"login": "agent"},
            "author_association": "NONE",
            "body": "CI green",
            "created_at": "2026-10-11T01:00:00Z",
        }
    ]
    ok2, reason2 = mrb_merge_gate.evaluate_merge_gate(no_board)
    assert ok2 is False
    assert "pass" in reason2.lower() or "board" in reason2.lower()

    good = [
        {
            "user": {"login": "agent"},
            "author_association": "NONE",
            "body": "## MRB board — #1 PASS\n\n**Verdict:** PASS\n",
            "created_at": "2026-10-11T02:00:00Z",
        }
    ]
    ok3, reason3 = mrb_merge_gate.evaluate_merge_gate(good)
    assert ok3 is True
    assert reason3 == ""

def test_job_mrb_skill_documents_fr3928_merge_gate():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #3928" in text
    assert "mrb_merge_gate" in text
    assert "on-hold" in text
    assert "**Verdict:** PASS" in text
