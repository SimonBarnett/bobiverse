"""FR #6203: self-review-deadlock still reports when no eligible reviewer.

FR #6112 dropped harvest tips from the waiting set and silenced author-only
idle when cloud eligibility cannot be checked (no home). With home present,
mrb_has_eligible_reviewer must still run so Copilot backoff + author-only
idle files a genuine deadlock.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import stall_detectors as sd


def _product_row(author: str, rid: str = "#1") -> dict:
    num = str(rid).lstrip("#")
    return {
        "task": "MRB",
        "repo": "SimonBarnett/bobiverse",
        "id": rid,
        "url": "https://github.com/SimonBarnett/bobiverse/pull/" + num,
        "title": "FR %s product" % rid,
        "author_seat": author,
    }


def test_fr6203_eligible_non_author_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1", "marchhare-1"},
            "idle": {"flamingo-1", "marchhare-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_author_only_without_home_still_silent_fr6112():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_harvest_lesson_mixed_still_silent_fr6112():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [
                _product_row("flamingo-1", "#6110"),
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6111",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6111",
                    "title": "lesson(bobiverse-fleet-ops): tip",
                    "labels": ["harvest-lesson"],
                    "author_seat": "flamingo-1",
                    "harvest_lesson": True,
                },
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6203_home_present_author_only_no_eligible_reports(tmp_path, monkeypatch):
    """With home, author-only idle and no eligible reviewer must file."""
    import copilot_dispatch as cd

    monkeypatch.setattr(cd, "mrb_reviewer_available", lambda *a, **k: False)
    monkeypatch.setattr(gitclaim, "mrb_has_eligible_reviewer", lambda *a, **k: False)
    found = sd.detect_self_review_deadlock(
        {
            "home": tmp_path,
            "live": {"flamingo-1"},
            "idle": {"flamingo-1"},
            "unaccepted": [_product_row("flamingo-1")],
            "accepted": [],
            "ledger": {},
            "now": 1_700_000_000.0,
        }
    )
    assert len(found) == 1
    assert found[0]["id"] == sd.SELF_REVIEW_ID
