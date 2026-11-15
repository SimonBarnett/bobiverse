"""FR #7522: pool reading staleness (tray, ear, Jeeves).

Si: \"It's not stale at 0% when we know when it comes back - it's only stale if
there are tokens left.\"

A pool with remaining 0% (or exhausted) and a known *future* reset / period_end
is never stale, whatever fetched_at age. Stale (red [stale] / exception report)
only when remaining > 0 (or reset unknown / past) and the reading is older than
``stale_after_s`` (default 120).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_STALE_AFTER_S = 120.0
FUTURE_SKEW_S = 120.0


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def remaining_pct_value(remaining: Any) -> float | None:
    """Return numeric remaining %, or None when unknown."""
    if remaining is None:
        return None
    if isinstance(remaining, bool):
        return None
    try:
        return float(remaining)
    except (TypeError, ValueError):
        s = str(remaining).strip().rstrip("%")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None


def exhausted_until_known_reset(
    *,
    remaining_pct: Any,
    period_end: Any = None,
    reset_at: Any = None,
    now: Any = None,
) -> bool:
    """True when remaining is 0 and reset/period_end is strictly in the future."""
    rem = remaining_pct_value(remaining_pct)
    if rem is None or rem > 0:
        return False
    end = _parse_utc(period_end if period_end is not None else reset_at)
    if end is None:
        return False
    now_dt = _parse_utc(now) or datetime.now(timezone.utc)
    return end > now_dt


def reading_age_seconds(fetched_at: Any, *, now: Any = None) -> float | None:
    fetched = _parse_utc(fetched_at)
    if fetched is None:
        return None
    now_dt = _parse_utc(now) or datetime.now(timezone.utc)
    return (now_dt - fetched).total_seconds()


def is_pool_reading_stale(
    *,
    fetched_at: Any,
    remaining_pct: Any = None,
    period_end: Any = None,
    reset_at: Any = None,
    now: Any = None,
    stale_after_s: float = DEFAULT_STALE_AFTER_S,
) -> bool:
    """True when the pool should show [stale] / raise a stale exception."""
    if exhausted_until_known_reset(
        remaining_pct=remaining_pct,
        period_end=period_end,
        reset_at=reset_at,
        now=now,
    ):
        return False
    age = reading_age_seconds(fetched_at, now=now)
    if age is None:
        # Missing fetched_at: stale unless exhausted-until-reset (already handled).
        return True
    if age < -FUTURE_SKEW_S:
        return True
    if age < 0:
        age = 0.0
    threshold = float(stale_after_s) if stale_after_s and float(stale_after_s) > 0 else DEFAULT_STALE_AFTER_S
    if threshold < 60:
        threshold = 60.0
    return age > threshold


def should_report_pool_stale_exception(
    *,
    fetched_at: Any,
    remaining_pct: Any = None,
    period_end: Any = None,
    reset_at: Any = None,
    now: Any = None,
    stale_after_s: float = DEFAULT_STALE_AFTER_S,
) -> bool:
    """Same rule as display staleness (FR #7522 / #7503 / #7504)."""
    return is_pool_reading_stale(
        fetched_at=fetched_at,
        remaining_pct=remaining_pct,
        period_end=period_end,
        reset_at=reset_at,
        now=now,
        stale_after_s=stale_after_s,
    )
