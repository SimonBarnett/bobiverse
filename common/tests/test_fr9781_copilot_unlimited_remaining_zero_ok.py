"""FR #9781: digest state=ok when unlimited=true even if remaining=0.

Live GitHub business quota can report unlimited=true, remaining=0,
percent_remaining=100, overage_permitted=false while CCA create still
succeeds. Never map remaining=0 alone to exhausted when unlimited is claimed.
Supersedes FR #7371 used-up reinterpretation for observation/digest.
"""
from __future__ import annotations

from pathlib import Path

import copilot_dispatch as cd


# Live REDQUEEN / digest shape (2026-11-24): unlimited + remaining=0 + create OK.
LIVE_UNLIMITED_REMAINING_ZERO = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 2343,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": False,
        }
    },
}


def test_fr9781_parse_unlimited_true_remaining_zero_is_ok():
    q = cd.parse_user_quota(LIVE_UNLIMITED_REMAINING_ZERO)
    assert q["unlimited"] is True
    assert q["state"] == "ok"
    assert q["remaining"] == 0
    assert q["percent_remaining"] == 100.0
    assert q["used"] == 2343
    assert q["overage_permitted"] is False


def test_fr9781_parse_finite_remaining_zero_still_exhausted():
    q = cd.parse_user_quota(
        {
            "quota_snapshots": {
                "premium_interactions": {
                    "unlimited": False,
                    "remaining": 0,
                    "percent_remaining": 0,
                    "credits_used": 9,
                    "overage_permitted": False,
                }
            }
        }
    )
    assert q["unlimited"] is False
    assert q["state"] == "exhausted"


def test_fr9781_pool_for_digest_unlimited_remaining_zero(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    cd.refresh_allowance(home, fetch_user=lambda: LIVE_UNLIMITED_REMAINING_ZERO, now=1.0)
    pool = cd.pool_for_digest(home)
    assert pool["unlimited"] is True
    assert pool["state"] == "ok"
    assert pool["remaining"] == 0
    assert cd.allowance_from_pool(pool) is True
    assert cd.has_allowance(home) is True


def test_fr9781_fail_when_remaining_zero_forces_exhausted_while_unlimited():
    """Pin: remaining=0 must not flip unlimited=true to exhausted."""
    q = cd.parse_user_quota(LIVE_UNLIMITED_REMAINING_ZERO)
    assert not (q["remaining"] == 0 and q["unlimited"] is True and q["state"] == "exhausted")
