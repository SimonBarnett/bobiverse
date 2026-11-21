"""FR #8634: stale holder_bored needs_human must not block a fresh seat."""
from __future__ import annotations

import gitclaim


def test_holder_bored_stamp_does_not_block_auto_offer():
    row = {
        "needs_human": True,
        "giveup_reason": "holder_bored",
        "giveup_seats": "flamingo-14448,flamingo-19720",
        "cooldown_until": "2026-11-20T17:15:59Z",
    }
    assert gitclaim.row_needs_human(row, "flamingo-24392") is False
    assert gitclaim.row_needs_human(row, "") is False
    assert gitclaim.row_has_false_needs_human(row) is True


def test_product_giveup_still_blocks():
    row = {
        "needs_human": True,
        "giveup_reason": "cannot review",
        "giveup_seats": "flamingo-14448",
    }
    assert gitclaim.row_needs_human(row, "flamingo-24392") is True
    assert gitclaim.row_has_false_needs_human(row) is False
