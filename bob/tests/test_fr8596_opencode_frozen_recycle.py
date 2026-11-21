# -*- coding: utf-8 -*-
"""FR #8596: recycle OpenCode seats when digest doing is frozen / progress stalled."""
from __future__ import annotations

import bob_worker as bw


def test_opencode_recycle_when_digest_doing_stale_without_ack():
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=False,
        digest_doing_age_s=4200.0,
        progress_moved_age_s=None,
        threshold_s=900.0,
    )
    assert reason == "opencode-lost-ack-stale"


def test_opencode_recycle_when_ack_open_but_no_log_turn_move():
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=2000.0,
        progress_moved_age_s=1800.0,
        threshold_s=900.0,
    )
    assert reason == "opencode-frozen-progress"


def test_opencode_no_recycle_under_hard_out_of_fuel_hold():
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=True,
        ack_open=True,
        digest_doing_age_s=5000.0,
        progress_moved_age_s=5000.0,
        threshold_s=900.0,
    )
    assert reason == ""


def test_opencode_no_recycle_when_recent_move_and_fresh_digest():
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=30.0,
        progress_moved_age_s=30.0,
        threshold_s=900.0,
    )
    assert reason == ""


def test_post_reassign_stale_digest_recycles_despite_progress_clock():
    """FR #8646: new seat after restart still recycles when worker.updated is frozen."""
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=1283.0,
        progress_moved_age_s=30.0,
        threshold_s=900.0,
    )
    assert reason == "opencode-frozen-progress"


def test_ack_open_digest_stale_without_progress_clock_recycles():
    """FR #8637: frozen worker.updated and no log/turn clock still recycles."""
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=939.0,
        progress_moved_age_s=None,
        threshold_s=900.0,
    )
    assert reason == "opencode-frozen-progress"


def test_week_limited_alone_is_not_out_of_fuel_for_gate():
    """Partial fuel (week limited, rolling rem>0) must not skip recycle (FR #8596)."""
    # Helper does not take week.limited; out_of_fuel must stay False for that case.
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,  # week.limited must not set this
        ack_open=False,
        digest_doing_age_s=3200.0,
        progress_moved_age_s=None,
        threshold_s=900.0,
    )
    assert reason == "opencode-lost-ack-stale"


def test_non_opencode_ignored():
    assert (
        bw.opencode_frozen_recycle_reason(
            kind="grok",
            out_of_fuel=False,
            ack_open=False,
            digest_doing_age_s=9999.0,
            progress_moved_age_s=9999.0,
            threshold_s=900.0,
        )
        == ""
    )


def test_threshold_env_helper_bounds():
    assert bw.opencode_frozen_progress_threshold_s(env={"BOB_WORKER_OPENCODE_FROZEN_PROGRESS_S": "900"}) == 900.0
    assert bw.opencode_frozen_progress_threshold_s(env={"BOB_WORKER_OPENCODE_FROZEN_PROGRESS_S": "30"}) >= 120.0

def test_digest_worker_doing_age_s():
    from datetime import datetime, timezone, timedelta
    import time

    now = time.time()
    old = (datetime.now(timezone.utc) - timedelta(seconds=1500)).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {
        "machines": {
            "flamingo": {
                "workers": [
                    {"nick": "flamingo-16764", "state": "doing", "updated": old},
                ]
            }
        }
    }
    age = bw.digest_worker_doing_age_s(doc, "flamingo-16764", now_wall=now)
    assert age is not None and age >= 1400
    assert bw.digest_worker_doing_age_s(doc, "flamingo-999", now_wall=now) is None

