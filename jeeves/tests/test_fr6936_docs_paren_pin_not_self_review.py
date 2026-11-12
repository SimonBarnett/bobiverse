"""FR #6936: docs(mrb-N) pin titles are pins; they must not file self-review-deadlock."""
from __future__ import annotations

import gitclaim
import stall_detectors as sd


def test_fr6936_docs_paren_title_is_docs_mrb_pin():
    assert gitclaim.is_docs_mrb_pin_pr(
        title="docs(mrb-6932): pin skill-dag MCP restart isolation"
    )
    assert gitclaim.is_lesson_or_pin_pr(
        title="docs(mrb-6932): pin skill-dag MCP restart isolation"
    )
    assert gitclaim.docs_mrb_pin_parent_pr_id(
        title="docs(mrb-6932): pin skill-dag MCP restart isolation"
    ) == "#6932"


def test_fr6936_docs_paren_pin_author_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-17568", "flamingo-6524"},
            "idle": {"flamingo-17568", "flamingo-6524"},
            "unaccepted": [
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6935",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6935",
                    "title": "docs(mrb-6932): pin skill-dag MCP restart isolation",
                    "author_seat": "flamingo-6524",
                }
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6936_slash_title_still_a_pin():
    assert gitclaim.is_docs_mrb_pin_pr(title="docs/mrb-6932 pin")
    assert gitclaim.docs_mrb_pin_parent_pr_id(title="docs/mrb-6932 pin") == "#6932"
