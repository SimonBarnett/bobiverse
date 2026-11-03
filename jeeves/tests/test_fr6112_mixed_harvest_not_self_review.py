"""FR #6112: harvest-lesson mixed with a product MRB is not a self-review stall.

#6106 skipped only when *every* waiting row was a lesson/pin. A product FR plus
its harvest tip (same author, author-only idle) still filed
stall:self-review-deadlock:#6110,#6111.
"""
from __future__ import annotations

import stall_detectors as sd


def test_fr6112_product_plus_harvest_author_only_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-47616"},
            "idle": {"flamingo-47616"},
            "unaccepted": [
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6110",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6110",
                    "title": "FR #6108: tighten airc Priority prepare scoping",
                    "author_seat": "flamingo-47616",
                },
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6111",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6111",
                    "title": "lesson(bobiverse-fleet-ops): Airc form prepare must never",
                    "labels": ["harvest-lesson", "via-intake"],
                    "author_seat": "flamingo-47616",
                    "harvest_lesson": True,
                },
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6112_product_author_only_idle_is_silent():
    found = sd.detect_self_review_deadlock(
        {
            "live": {"flamingo-47616"},
            "idle": {"flamingo-47616"},
            "unaccepted": [
                {
                    "task": "MRB",
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#6110",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/6110",
                    "title": "FR #6108 product",
                    "author_seat": "flamingo-47616",
                }
            ],
            "accepted": [],
            "ledger": {},
        }
    )
    assert found == []


def test_fr6112_cross_author_product_still_deadlocks():
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
