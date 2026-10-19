"""FR #4827: ack-stale must not release a live agent; idle past the quiet window still does."""
from __future__ import annotations

import time

from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_active_agent_still_held_at_45_min():
    """Process I/O inside the quiet window keeps the ACK past ack_stale_s (45 min)."""
    clock = FakeClock(0.0)
    e, sent, _logs = _emitter(
        clock,
        harvest_hold_s=0.0,
        done_miss_grace_s=20.0,
        ack_stale_s=2700.0,
        ack_quiet_s=120.0,
        idle_s=30.0,
        repeat_s=30.0,
    )
    e.on_outbox("ACK FR SimonBarnett/bobiverse#4827")
    clock.advance(2690.0)
    e.note_agent_active()
    clock.advance(30.0)  # 2720s since ACK; last I/O 30s ago
    time.sleep(0.15)
    assert e.ack_open is True
    assert not any(r == "idle" for _t, r in e.sent)
    e.stop()


def test_open_turn_still_held_at_45_min():
    clock = FakeClock(0.0)
    e, sent, _logs = _emitter(
        clock,
        harvest_hold_s=0.0,
        done_miss_grace_s=20.0,
        ack_stale_s=2700.0,
        ack_quiet_s=60.0,
        idle_s=30.0,
        repeat_s=30.0,
    )
    e.on_outbox("ACK FR SimonBarnett/bobiverse#4827")
    e.turn_started(at=clock())
    clock.advance(2710.0)
    time.sleep(0.15)
    assert e.ack_open is True
    assert not any(r == "idle" for _t, r in e.sent)
    e.stop()


def test_idle_past_quiet_window_still_releases():
    """No turn, and the last I/O is older than both ack_stale_s and ack_quiet_s."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=0.0,
        done_miss_grace_s=20.0,
        ack_stale_s=60.0,
        ack_quiet_s=30.0,
        idle_s=5.0,
        repeat_s=5.0,
    )
    e.on_outbox("ACK FR o/r#4827")
    e.note_agent_active()
    n0 = len(sent)
    clock.advance(61.0)
    assert _wait(lambda: any(r == "ack-stale" for _t, r in e.sent[n0:]), clock, timeout=5.0)
    assert not any("done-miss armed" in m for m in logs)
    e.stop()


def test_stand_down_clears_matching_ack():
    clock = FakeClock(0.0)
    e, _sent, logs = _emitter(
        clock,
        harvest_hold_s=90.0,
        ack_stale_s=2700.0,
        idle_s=30.0,
        repeat_s=30.0,
    )
    e.on_outbox("ACK FR SimonBarnett/a-search#4428")
    assert e.note_stand_down("SimonBarnett/a-search#4428") is True
    assert e.ack_open is False
    assert any("stand down" in m for m in logs)
    e.stop()
