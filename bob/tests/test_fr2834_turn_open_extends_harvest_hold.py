"""FR #2834: harvest_hold_s must not release while a post-DONE turn is still open."""
from __future__ import annotations

import time

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_fr2834_open_turn_blocks_bored_past_harvest_hold():
    """DONE at t=0 with turn already open: no !bored at t=90; turn_ended at t=120 fires once."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.on_outbox("ACK FR o/r#2834")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#2834 https://example.com/p/2834")
    n0 = len(sent)
    clock.advance(90.0)
    time.sleep(0.05)
    assert len(sent) == n0, "must not !bored while turn still open after harvest_hold_s"
    clock.advance(30.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    assert any("hold released" in m for m in logs)
    e.stop()


def test_fr2834_turn_hold_max_releases_without_turn_ended():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=120.0)
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#1 https://example.com/p/1")
    n0 = len(sent)
    clock.advance(90.0)
    time.sleep(0.05)
    assert len(sent) == n0
    clock.advance(35.0)  # past hold_started + 120
    assert _wait(lambda: len(sent) > n0, clock, timeout=3.0)
    assert e.sent[-1][1] == "done"
    assert any("turn hold max" in m for m in logs)
    e.stop()


def test_fr2834_no_turn_signal_keeps_harvest_hold_fallback():
    """Watcher never saw turn_started: !bored still at harvest_hold_s."""
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.on_outbox("DONE FR o/r#2 https://example.com/p/2")
    n0 = len(sent)
    clock.advance(89.0)
    time.sleep(0.05)
    assert len(sent) == n0
    clock.advance(2.0)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    e.stop()


def test_fr2834_holding_assigns_while_turn_open_past_harvest():
    clock = FakeClock(0.0)
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#3 https://example.com/p/3")
    relay.hold_assigns_while = lambda: e.holding_incoming_assigns
    relay.on_hold_assign = lambda line: e.note_held_assign()
    clock.advance(95.0)
    assert e.holding_incoming_assigns is True
    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: MRB SimonBarnett/bobiverse#9 https://github.com/SimonBarnett/bobiverse/pull/9",
    )
    assert st == "held_until_turn_end"
    assert injected == []
    e.turn_ended(at=clock())
    e.clear_held_assign()
    assert relay.release_held_assigns() >= 1
    assert len(injected) == 1
    e.stop()
