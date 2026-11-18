"""FR #8264: a self-review stall FR is not offered to the idle author."""
from __future__ import annotations

import gitclaim


def _stall_row() -> dict:
    return {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8264",
        "title": "stall:self-review-deadlock:SimonBarnett/bobiverse#8239",
        "body": (
            '{"idle": ["flamingo-4392"], "waiting": ["SimonBarnett/bobiverse#8239"]}'
        ),
    }


def test_fr8264_author_blocked_other_seat_not():
    row = _stall_row()
    assert gitclaim.seat_blocked_for_self_review_stall(row, "flamingo-4392") is True
    assert gitclaim.seat_blocked_for_self_review_stall(row, "marchhare-1") is False


def test_fr8264_product_fr_without_stall_is_not_blocked():
    row = {
        "task": "FR",
        "title": "FR: something else",
        "body": '{"idle": ["flamingo-4392"]}',
    }
    assert gitclaim.seat_blocked_for_self_review_stall(row, "flamingo-4392") is False


def test_fr8264_live_author_cannot_take_stall_sibling_can():
    row = _stall_row()
    assert gitclaim.live_seat_can_take_unanswered(row, {"flamingo-4392"}) is False
    assert gitclaim.live_seat_can_take_unanswered(row, {"flamingo-4392", "marchhare-1"}) is True


def test_fr8293_author_blocked_when_stall_body_has_no_idle_list():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8293",
        "title": "stall:self-review-deadlock:SimonBarnett/bobiverse#8239,SimonBarnett/bobiverse#8273",
        "body": "",
    }
    doc = {
        "unaccepted": [
            {
                "task": "MRB",
                "repo": "SimonBarnett/bobiverse",
                "id": "#8273",
                "author_seat": "flamingo-4392",
            }
        ]
    }
    assert gitclaim.seat_blocked_for_self_review_stall(row, "flamingo-4392", doc) is True
    assert gitclaim.seat_blocked_for_self_review_stall(row, "marchhare-1", doc) is False
