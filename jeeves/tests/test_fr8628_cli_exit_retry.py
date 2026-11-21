"""FR #8628: one auto-offer after agent-cli-nonzero-exit, then needs_human holds."""
from __future__ import annotations

import gitclaim


def _row(**extra):
    base = {
        "needs_human": True,
        "giveup_reason": "agent-cli-nonzero-exit",
        "giveup_seats": "redqueen-7276,flamingo-10896",
        "cooldown_until": "2026-11-20T21:05:45Z",
    }
    base.update(extra)
    return base


def test_fresh_nick_passes_once_after_cooldown():
    row = _row()
    now = 1.8e9  # well after 2026-11-20
    assert gitclaim.cli_exit_fresh_seat_retry(row, "flamingo-24392", now) is True
    assert gitclaim.cli_exit_fresh_seat_retry(row, "flamingo-24392", 1.0) is False
    assert gitclaim.row_needs_human(row, "flamingo-24392") is False
    assert gitclaim.row_needs_human(row, "") is True
    assert gitclaim.row_needs_human(row, "flamingo-10896") is True


def test_other_reason_and_used_flag_stay_blocked():
    now = 1.8e9
    other = _row(giveup_reason="cannot review")
    assert gitclaim.cli_exit_fresh_seat_retry(other, "flamingo-24392", now) is False
    assert gitclaim.row_needs_human(other, "flamingo-24392") is True
    used = _row(cli_exit_retry_used=True)
    assert gitclaim.cli_exit_fresh_seat_retry(used, "flamingo-24392", now) is False
    assert gitclaim.row_needs_human(used, "flamingo-24392") is True


def test_stamp_spends_the_one_retry():
    row = _row()
    gitclaim.stamp_cli_exit_retry_used(row)
    assert row["cli_exit_retry_used"] is True
    assert gitclaim.row_needs_human(row, "flamingo-99999") is True
    plain = {"needs_human": False, "giveup_reason": "agent-cli-nonzero-exit"}
    gitclaim.stamp_cli_exit_retry_used(plain)
    assert "cli_exit_retry_used" not in plain
