"""MRB #3930 hostile pins for FR #3928 hold + PASS board merge gate."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_gate = importlib.import_module("mrb_merge_gate")
gitclaim = importlib.import_module("gitclaim")


def test_mrb3930_cli_exit_2_on_hold(monkeypatch):
    comments = [
        {
            "author_association": "OWNER",
            "body": "On hold: must not merge until #1358.",
            "created_at": "2026-10-10T13:53:22Z",
        }
    ]
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", lambda *a, **k: comments)
    assert mrb_merge_gate.main(["SimonBarnett/a-search", "1334"]) == 2


def test_mrb3930_cli_exit_2_without_pass_board(monkeypatch):
    comments = [
        {
            "author_association": "NONE",
            "body": "CI green",
            "created_at": "2026-10-11T01:00:00Z",
        }
    ]
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", lambda *a, **k: comments)
    assert mrb_merge_gate.main(["SimonBarnett/bobiverse", "3930"]) == 2


def test_mrb3930_cli_exit_0_when_pass_board(monkeypatch):
    comments = [
        {
            "author_association": "NONE",
            "body": "## MRB board — #3930 PASS\n\n**Verdict:** PASS\n",
            "created_at": "2026-10-11T03:36:00Z",
        }
    ]
    monkeypatch.setattr(mrb_merge_gate, "fetch_issue_comments", lambda *a, **k: comments)
    assert mrb_merge_gate.main(["SimonBarnett/bobiverse", "3930"]) == 0


def test_mrb3930_collaborator_hold_counts():
    comments = [
        {
            "author_association": "COLLABORATOR",
            "body": "Do not merge this PR until auth lands.",
            "created_at": "2026-10-10T12:00:00Z",
        }
    ]
    assert mrb_merge_gate.find_active_owner_hold(comments) is not None


def test_mrb3930_skill_fr3928_contiguous_and_mermaid_board_before_merge():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    raw = skill.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    needle = (
        "**CAST IRON (FR #3928):** never merge a PR that is on hold, and never merge "
        "without a posted MRB PASS board."
    )
    assert needle in text
    assert "mrb_merge_gate.py" in text
    # Mermaid: board node before merge; no premature "Merge original + fix PR" node
    assert 'L["Post the MRB board PASS first (FR #3928)"]' in text
    assert "Merge original + fix PR" not in text
    assert 'G2["mrb_merge_gate: no owner hold + PASS board present"]' in text
    # FAIL path feeds board, not a pre-board merge node
    assert "G --> L" in text
    assert "G --> H" not in text


def test_mrb3930_hold_label_wip_blocks_offer():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "1",
        "url": "https://github.com/SimonBarnett/a-search/pull/1",
        "labels": ["wip"],
    }
    assert gitclaim.mrb_row_offerable(row) is False
