"""FR #9364: DONE/GIVEUP with no open turn skips harvest_hold; flush held assigns now.

When GrokTurnWatcher never sees turn_started/turn_ended, the old path waited the full
harvest_hold_s (~90s) before releasing parked assigns (offer→inject 2–3 min). With no
live turn, skip the clock and inject promptly. Open-turn cases still wait for
turn_ended (FR #2834 / #7265).
"""
from __future__ import annotations

import time

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_fr9364_done_with_no_turn_signal_skips_harvest_hold():
    """DONE and watcher never armed → !bored within seconds, not harvest_hold_s."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#9364")
    clock.advance(1.0)
    n0 = len(sent)
    e.on_outbox("DONE FR o/r#9364 https://example.com/p/9364")
    assert _wait(lambda: len(sent) > n0, clock, timeout=2.0)
    assert e.sent[-1][1] == "done"
    assert e.sent[-1][0] < 10.0
    assert any("skip harvest hold (no open turn)" in m for m in logs)
    assert not any("fallback timer, no turn_ended seen" in m for m in logs)
    assert not any("harvest hold 90s fallback" in m for m in logs)
    e.stop()


def test_fr9364_giveup_with_no_turn_signal_skips_and_does_not_park():
    """GIVEUP with no open turn → holding_incoming_assigns false; next assign injects."""
    clock = FakeClock(0.0)
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, idle_s=9999.0, repeat_s=9999.0)
    e.start()
    e.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in e.sent), clock)
    relay.hold_assigns_while = lambda: e.holding_incoming_assigns
    relay.on_hold_assign = lambda line: e.note_held_assign()

    e.on_outbox("GIVEUP FR SimonBarnett/bobiverse#1")
    assert any("skip harvest hold (no open turn)" in m for m in logs)
    assert e.holding_incoming_assigns is False

    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#9 https://github.com/SimonBarnett/bobiverse/issues/9",
    )
    assert st in ("ok", "injected")
    assert len(injected) == 1
    assert "bobiverse#9" in injected[0].lower()
    e.stop()


def test_fr9364_held_assign_flushed_on_giveup_skip():
    """Parked assign is flushed immediately when GIVEUP skips harvest (no open turn)."""
    clock = FakeClock(0.0)
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0)
    e.relay = relay
    # Pre-park as if ACK-on-receipt held the next job during a prior miss path.
    line = (
        "marchhare-1: FR SimonBarnett/bobiverse#3 "
        "https://github.com/SimonBarnett/bobiverse/issues/3"
    )
    with relay._lock:
        relay._pending.append(line)
    e.note_held_assign()
    assert injected == []

    e.on_outbox("GIVEUP FR SimonBarnett/bobiverse#99")
    assert any("skip harvest hold (no open turn)" in m for m in logs)
    assert any("released" in m and "held assign" in m for m in logs)
    assert len(injected) == 1
    assert "bobiverse#3" in injected[0].lower()
    e.stop()


def test_fr9364_open_turn_still_waits_for_turn_ended():
    """DONE while turn open still holds until turn_ended (FR #2834 unchanged)."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.on_outbox("ACK FR o/r#9364")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#9364 https://example.com/p/9364")
    n0 = len(sent)
    assert any("harvest hold 90s fallback" in m for m in logs)
    clock.advance(20.0)
    time.sleep(0.05)
    assert len(sent) == n0
    e.turn_ended(at=clock())
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    assert any("hold released" in m for m in logs)
    e.stop()


def test_fr9364_done_after_turn_ended_still_skips():
    """DONE after turn_ended keeps the FR #7265 skip path (turn already ended)."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#9364")
    clock.advance(1.0)
    e.turn_started(at=clock(), turn=1)
    clock.advance(2.0)
    e.turn_ended(at=clock(), turn=1)
    n0 = len(sent)
    clock.advance(0.2)
    e.on_outbox("DONE FR o/r#9364 https://example.com/p/9364")
    assert _wait(lambda: len(sent) > n0, clock, timeout=2.0)
    assert any("skip harvest hold (turn already ended)" in m for m in logs)
    e.stop()
