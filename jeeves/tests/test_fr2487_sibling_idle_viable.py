"""FR #2487: sibling MRB block only when another machine has an idle/free seat."""
from __future__ import annotations

import gitclaim


def _mrb(author: str) -> dict:
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#2487",
        "title": "fix: sibling idle viable",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/2487",
        "author_seat": author,
        "implementer_seat": author,
    }


def test_fr2487_sibling_not_blocked_when_other_machine_seats_busy():
    row = _mrb("marchhare-35016")
    live = {
        "marchhare-35016",
        "marchhare-40208",
        "win-mpre8vi4u6u-14452",
        "win-mpre8vi4u6u-7764",
    }
    # ionos busy => not in free
    free = {"marchhare-35016", "marchhare-40208"}
    assert gitclaim.review_blocked_for_author(row, "marchhare-35016", live, free=free) is True  # exact
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=free) is False  # sibling OK


def test_fr2487_sibling_blocked_when_other_machine_has_free_seat():
    row = _mrb("marchhare-35016")
    live = {
        "marchhare-35016",
        "marchhare-40208",
        "win-mpre8vi4u6u-14452",
        "win-mpre8vi4u6u-7764",
    }
    free = {"marchhare-35016", "marchhare-40208", "win-mpre8vi4u6u-7764"}  # ionos free
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=free) is True


def test_fr2487_free_none_preserves_legacy_live_as_free():
    row = _mrb("marchhare-35016")
    live = {"marchhare-35016", "marchhare-40208", "win-mpre8vi4u6u-7764"}
    # free=None => treat all live as free => sibling blocked
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=None) is True
