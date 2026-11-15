"""FR #7522: 0% with known future reset is not stale (tray/ear/Jeeves rule)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pool_reading_stale as prs  # noqa: E402

NOW = "2026-11-15T15:30:00Z"
OLD = "2026-11-15T10:00:00Z"  # >2 min old
FUTURE = "2026-12-01T00:00:00Z"
PAST = "2026-11-01T00:00:00Z"


def test_fr7522_zero_pct_future_reset_not_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=FUTURE,
            now=NOW,
        )
        is False
    )
    assert (
        prs.should_report_pool_stale_exception(
            fetched_at=OLD,
            remaining_pct=0,
            reset_at=FUTURE,
            now=NOW,
        )
        is False
    )


def test_fr7522_zero_pct_past_reset_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=PAST,
            now=NOW,
        )
        is True
    )


def test_fr7522_zero_pct_unknown_reset_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=0,
            period_end=None,
            now=NOW,
        )
        is True
    )


def test_fr7522_fifty_pct_old_is_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at=OLD,
            remaining_pct=50,
            period_end=FUTURE,
            now=NOW,
        )
        is True
    )


def test_fr7522_fifty_pct_fresh_not_stale():
    assert (
        prs.is_pool_reading_stale(
            fetched_at="2026-11-15T15:29:00Z",
            remaining_pct=50,
            period_end=FUTURE,
            now=NOW,
        )
        is False
    )


def test_fr7522_exhausted_held_helper():
    assert prs.exhausted_until_known_reset(
        remaining_pct=0, period_end=FUTURE, now=NOW
    )
    assert not prs.exhausted_until_known_reset(
        remaining_pct=1, period_end=FUTURE, now=NOW
    )
