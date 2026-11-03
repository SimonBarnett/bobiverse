"""FR #6106: harvest-lesson MRB waiting on its author is not a self-review stall FR."""
from __future__ import annotations

import stall_detectors as sd


def test_fr6106_harvest_lesson_author_only_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-47616"},
            "idle": {"flamingo-47616"},
            "unaccepted": [
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6105",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6105",
                    "title": "lesson(harvest): After heal_bored_latency queues !recycleseat",
                    "labels": ["harvest-lesson", "via-intake"],
                    "author_seat": "flamingo-47616",
                    "harvest_lesson": True,
                }
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6106_cross_author_product_mrb_still_deadlocks():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-1", "marchhare-1"},
            "idle": {"flamingo-1", "marchhare-1"},
            "unaccepted": [
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#1",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/1",
                    "title": "FR #1 product",
                    "author_seat": "flamingo-1",
                    "giveup_seats": "marchhare-1",
                },
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#2",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/2",
                    "title": "FR #2 product",
                    "author_seat": "marchhare-1",
                    "giveup_seats": "flamingo-1",
                },
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert len(found) == 1
    assert found[0]["id"] == sd.SELF_REVIEW_ID
