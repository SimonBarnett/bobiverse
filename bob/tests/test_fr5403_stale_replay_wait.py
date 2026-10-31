"""FR #5403: defer stale-replay compare until transcript shows J or wait elapses."""
from __future__ import annotations

import bob_worker as bw


def test_fr5403_ready_when_transcript_is_open_ack():
    assert (
        bw.stale_replay_compare_ready(
            user_key="MRB o/r#2",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,
            now=101.0,
            wait_s=8.0,
        )
        is True
    )


def test_fr5403_wait_while_lag_shows_old_key():
    assert (
        bw.stale_replay_compare_ready(
            user_key="FR o/r#1",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,
            now=101.0,
            wait_s=8.0,
        )
        is False
    )
    assert (
        bw.stale_replay_compare_ready(
            user_key="FR o/r#1",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,
            now=109.0,
            wait_s=8.0,
        )
        is True
    )


def test_fr5403_turn_started_for_open_skips_wait():
    assert (
        bw.stale_replay_compare_ready(
            user_key="FR o/r#1",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,
            now=101.0,
            wait_s=8.0,
            turn_started_for_open=True,
        )
        is True
    )


def test_fr5403_done_exemption_still_holds_after_ready():
    assert (
        bw.stale_replay_assign_key(
            user_key="FR o/r#1",
            finished_keys={"FR o/r#1"},
            open_ack_key="MRB o/r#2",
            done_keys={"FR o/r#1"},
        )
        is None
    )


def test_fr5403_pins():
    from pathlib import Path

    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "FR #5403" in src
    assert "stale_replay_compare_ready" in src
    assert "_cursor_stale_replay_check" in src
    assert "BOB_WORKER_STALE_REPLAY_WAIT_S" in src
    assert not Path(bw.__file__).read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5403_ack_at_is_wait_origin_after_inject_cleared():
    """MRB #5435: after ACK clears _inject_at, wait must still defer on lag."""
    # Simulate call site passing _ack_at when _inject_at is None.
    assert (
        bw.stale_replay_compare_ready(
            user_key="FR o/r#1",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,  # ack_at
            now=101.0,
            wait_s=8.0,
        )
        is False
    )
    assert (
        bw.stale_replay_compare_ready(
            user_key="FR o/r#1",
            open_ack_key="MRB o/r#2",
            inject_at=100.0,
            now=109.0,
            wait_s=8.0,
        )
        is True
    )


def test_mrb5435_call_site_uses_ack_at_fallback():
    from pathlib import Path

    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "_ack_at" in src
    assert "wait_from" in src
    assert "MRB #5435" in src
