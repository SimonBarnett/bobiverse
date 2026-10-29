"""FR #5203: bored-latency must not fire on a seat that just ACK/DONE'd a job.

flamingo-48304: last !bored was 313s ago because the seat was busy, then idle
with a stale last_bored stamp. Shop verbs and last_activity reset the clock.
"""
from __future__ import annotations

import stall_detectors as sd


def test_shop_verbs_reset_bored_clock():
    import gitclaim

    assert gitclaim.shop_line_resets_bored_clock("DONE FR SimonBarnett/bobiverse#1 https://x")
    assert gitclaim.shop_line_resets_bored_clock("ACK MRB SimonBarnett/hrsmith#2")
    assert gitclaim.shop_line_resets_bored_clock("NACK FR x/y#1 reason")
    assert gitclaim.shop_line_resets_bored_clock("GIVEUP FR x/y#1 hung")
    assert not gitclaim.shop_line_resets_bored_clock("!bored")
    assert not gitclaim.shop_line_resets_bored_clock("hello")


def test_stale_last_bored_with_recent_activity_is_silent():
    now = 100_000.0
    assert (
        sd.detect_bored_latency(
            {
                "now": now,
                "idle": {"flamingo-48304"},
                "last_bored": {"flamingo-48304": now - 313},
                "last_activity": {"flamingo-48304": now - 10},
            }
        )
        == []
    )


def test_accepted_seat_is_not_bored_latency():
    now = 100_000.0
    assert (
        sd.detect_bored_latency(
            {
                "now": now,
                "idle": {"flamingo-48304"},
                "last_bored": {"flamingo-48304": now - 313},
                "accepted": [{"accepted_by": "flamingo-48304", "repo": "x", "id": "#1"}],
            }
        )
        == []
    )


def test_truly_idle_stale_last_bored_still_fires():
    now = 100_000.0
    late = sd.detect_bored_latency(
        {
            "now": now,
            "idle": {"flamingo-48304"},
            "last_bored": {"flamingo-48304": now - 313},
            "accepted": [],
        }
    )
    assert late and late[0]["id"] == sd.BORED_LATENCY_ID
    assert late[0]["evidence"]["lag_s"] == 313


def test_irc_agent_stamps_last_bored_on_shop_verbs():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    claim = src[src.find("def _maybe_git_claim") : src.find("def _git_bored")]
    assert "shop_line_resets_bored_clock" in claim
    assert "record_last_bored" in claim


def test_chair_snap_passes_last_activity():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py").read_text(
        encoding="utf-8"
    )
    scan = src[src.find("def _stall_scan") :]
    assert '"last_activity"' in scan or "'last_activity'" in scan
    assert "last_worker_activity" in scan
