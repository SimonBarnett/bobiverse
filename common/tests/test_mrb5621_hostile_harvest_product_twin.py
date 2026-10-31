"""MRB #5621 hostile pins for FR #5606 harvest product-PR twin."""
from __future__ import annotations

import intake


def test_mrb5621_no_bullets_never_token_twins():
    pr = {
        "title": "FR #1: widget",
        "body": "returns none true bool write claim. No markdown list.",
        "labels": [],
        "number": 1,
        "repo": "SimonBarnett/bobiverse",
    }
    assert not intake._harvest_pr_matches_lessons(
        pr,
        ["CredMan apply must return wrote bool not None"],
        new_title="harvest: CredMan wrote",
    )


def test_mrb5621_generic_only_bullet_does_not_cover():
    assert not intake.harvest_pr_covers_new_lesson(
        "lesson(harvest): returns none",
        "- returns none true false",
        "CredMan apply wrote bool must not be void",
        new_title="harvest: CredMan",
    )
