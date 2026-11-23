# -*- coding: utf-8 -*-
"""FR #9009: recent opencode-turns.jsonl activity suppresses frozen-progress recycle."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bob_worker as bw


def _iso(offset_s: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def test_probe_opencode_turns_recent_true_for_fresh_turn_started(tmp_path: Path):
    p = tmp_path / "opencode-turns.jsonl"
    now = time.time()
    rows = [
        {"type": "turn_ended", "ts": _iso(-120), "turn_number": 1},
        {"type": "turn_started", "ts": _iso(-5), "turn_number": 2},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert bw.probe_opencode_turns_recent(p, within_s=900.0, now_wall=now) is True


def test_probe_opencode_turns_recent_false_when_stale(tmp_path: Path):
    p = tmp_path / "opencode-turns.jsonl"
    now = time.time()
    rows = [
        {"type": "turn_started", "ts": _iso(-2000), "turn_number": 1},
        {"type": "turn_ended", "ts": _iso(-1900), "turn_number": 1},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert bw.probe_opencode_turns_recent(p, within_s=900.0, now_wall=now) is False


def test_fr9009_digest_stale_but_recent_turns_do_not_recycle():
    """Redqueen #9009: turns still flowing while digest stamp looked frozen."""
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=1283.0,
        progress_moved_age_s=30.0,
        threshold_s=900.0,
        turns_recent=True,
    )
    assert reason == ""


def test_fr8646_still_recycles_without_recent_turns():
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=True,
        digest_doing_age_s=1283.0,
        progress_moved_age_s=30.0,
        threshold_s=900.0,
        turns_recent=False,
    )
    assert reason == "opencode-frozen-progress"
def test_fr9009_lost_ack_stale_still_recycles_with_recent_turns():
    """ACK never opened: recent turns do not suppress lost-ack-stale."""
    reason = bw.opencode_frozen_recycle_reason(
        kind="opencode",
        out_of_fuel=False,
        ack_open=False,
        digest_doing_age_s=4200.0,
        progress_moved_age_s=None,
        threshold_s=900.0,
        turns_recent=True,
    )
    assert reason == "opencode-lost-ack-stale"
