"""FR #2811: hold Jeeves assigns during harvest hold; deliver on turn_ended (or hold expiry)."""
from __future__ import annotations

import threading
import time

import bob_worker as bw


class FakeClock:
    """Matches test_fr2802: advance wakes registered BoredEmitter Conditions."""

    def __init__(self, t: float = 0.0):
        self.t = float(t)
        self._emitters: list = []

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += float(dt)
        for e in self._emitters:
            with e._cv:
                e._cv.notify_all()
        return self.t


def _wait(pred, clock: FakeClock, timeout: float = 2.0, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        clock.advance(step)
        time.sleep(0.005)
    return pred()


def test_fr2811_assign_held_during_harvest_until_turn_ended():
    clock = FakeClock(0.0)
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)
    sent: list = []
    bored = bw.BoredEmitter(
        lambda: sent.append(clock()) or True,
        lambda m: None,
        clock=clock,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
    )
    clock._emitters.append(bored)
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)
    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    relay.on_hold_assign = lambda line: bored.note_held_assign()

    # drain_outbox passes the colon body (not the PRIVMSG wrapper) into on_outbox.
    bored.on_outbox("GIVEUP MRB SimonBarnett/bobiverse#1 self-MRB")
    assert bored.holding_incoming_assigns is True

    status = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: MRB SimonBarnett/bobiverse#2 https://github.com/SimonBarnett/bobiverse/pull/2",
    )
    assert status == "held_until_turn_end"
    assert injected == []

    clock.advance(12.0)
    bored.turn_ended(at=clock())
    bored.clear_held_assign()
    flushed = relay.release_held_assigns()
    assert flushed >= 1
    assert len(injected) == 1
    assert "bobiverse#2" in injected[0].lower()
    assert bored.holding_incoming_assigns is False
    bored.stop()


def test_fr2811_nothing_queued_still_skipped_during_hold():
    clock = FakeClock(0.0)
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=clock)
    relay.set_target(lambda line: injected.append(line) or True)
    bored = bw.BoredEmitter(
        lambda: True,
        lambda m: None,
        clock=clock,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
    )
    clock._emitters.append(bored)
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)
    bored.on_outbox("GIVEUP FR SimonBarnett/bobiverse#1")
    assert bored.holding_incoming_assigns is True
    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    st = relay.deliver("Jeeves", "#marchhare", "marchhare-1: nothing queued")
    assert st == "skipped"
    assert injected == []
    bored.stop()


def test_fr2811_harvest_fallback_flushes_held_assign_before_bored():
    """No turn_ended: free/done fire runs post_bored, which flushes before !bored."""
    clock = FakeClock(0.0)
    injected: list[str] = []
    bored_sent: list = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)

    def post_bored() -> bool:
        # Mirror Supervisor.post_bored FR #2811 flush-before-!bored.
        bored.clear_held_assign()
        n = relay.release_held_assigns()
        if n:
            # Injected assign is new work: suppress !bored this tick.
            bored.activity(mark_work=True)
            return False
        bored_sent.append(clock())
        return True

    bored = bw.BoredEmitter(
        post_bored,
        lambda m: None,
        clock=clock,
        harvest_hold_s=5.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )
    clock._emitters.append(bored)
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)
    n_start = len(bored_sent)
    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    relay.on_hold_assign = lambda line: bored.note_held_assign()

    bored.on_outbox("GIVEUP FR SimonBarnett/bobiverse#1")
    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#9 https://github.com/SimonBarnett/bobiverse/issues/9",
    )
    assert st == "held_until_turn_end"
    assert injected == []

    clock.advance(6.0)
    assert _wait(lambda: len(injected) >= 1, clock)
    assert "bobiverse#9" in injected[0].lower()
    # Flush suppresses the free !bored; inject-pending keeps later retries quiet.
    time.sleep(0.2)
    clock.advance(1.0)
    assert len(bored_sent) == n_start
    bored.stop()
