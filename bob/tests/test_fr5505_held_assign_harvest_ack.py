"""FR #5505: assign held during post-NACK harvest hold must inject when hold ends.

Production path: ACK-on-receipt writes through write_outbox -> BoredEmitter.on_outbox,
which must not cancel the harvest hold while the assign is still parked. When the hold
ends with no agent turn, release_held_assigns must inject (even if a free !bored is
still pending). Watchdog: ACKed-held-not-injected past a short deadline injects or
GIVEUPs so Jeeves never keeps an accepted row forever.
"""
from __future__ import annotations

import time

import bob_worker as bw


class FakeClock:
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


def _wait(pred, clock: FakeClock, timeout: float = 3.0, step: float = 0.02) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        clock.advance(step)
        time.sleep(0.005)
    return pred()


NACK_LINE = "NACK FR SimonBarnett/bobiverse#5459 already finished"
ASSIGN_LINE = (
    "marchhare-1: MRB SimonBarnett/bobiverse#5484 "
    "https://github.com/SimonBarnett/bobiverse/pull/5484"
)


def test_fr5505_nack_harvest_hold_ack_on_receipt_injects_when_hold_ends():
    """turn end -> NACK -> harvest hold -> assign during hold (ACK on receipt) -> no turn
    -> assign must be injected within harvest_hold_s + margin.
    """
    clock = FakeClock(0.0)
    injected: list[str] = []
    outbox: list[str] = []
    logs: list[str] = []
    bored_sent: list = []

    relay = bw.Relay(log=logs.append, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)

    def post_bored() -> bool:
        bored.clear_held_assign()
        n = relay.release_held_assigns()
        if n:
            bored.activity(mark_work=True)
            return False
        bored_sent.append(clock())
        return True

    bored = bw.BoredEmitter(
        post_bored,
        logs.append,
        clock=clock,
        harvest_hold_s=5.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
        assign_grace_s=600.0,
        ack_stale_s=2700.0,
    )
    clock._emitters.append(bored)
    bored.relay = relay
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)

    # Production wiring: ACK-on-receipt goes through seat outbox into BoredEmitter.
    def write_outbox(text: str) -> bool:
        outbox.append(text)
        bored.on_outbox(text)
        return True

    relay.write_outbox = write_outbox
    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    relay.on_hold_assign = lambda line: bored.note_held_assign()

    # Prior turn already ended; NACK starts post-free harvest hold (issue sequence).
    bored.turn_ended(at=clock())
    clock.advance(0.1)
    bored.on_outbox(NACK_LINE)
    assert bored.holding_incoming_assigns is True

    st = relay.deliver("Jeeves", "#marchhare", ASSIGN_LINE)
    assert st == "held_until_turn_end"
    assert injected == []
    assert any(x.startswith("ACK MRB SimonBarnett/bobiverse#5484") for x in outbox)
    # Harvest hold must survive ACK-on-receipt while the assign is still parked.
    assert bored.holding_incoming_assigns is True, (
        "ACK-on-receipt must not cancel harvest hold while assign is still held"
    )

    # No turn follows. Past harvest_hold_s the parked assign must inject.
    clock.advance(6.0)
    assert _wait(lambda: len(injected) >= 1, clock, timeout=4.0), (
        f"held assign must inject after harvest expiry; injected={injected!r} logs={logs[-8:]!r}"
    )
    assert "bobiverse#5484" in injected[0].lower()
    assert relay.has_pending_work() is False
    bored.stop()


def test_fr5505_acked_held_watchdog_injects_without_turn():
    """If an ACKed held assign is never flushed (e.g. harvest cleared), watchdog injects."""
    clock = FakeClock(0.0)
    injected: list[str] = []
    outbox: list[str] = []
    logs: list[str] = []

    relay = bw.Relay(log=logs.append, clock=clock, max_pending=8)
    relay.set_target(lambda line: injected.append(line) or True)

    bored = bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=clock,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
        assign_grace_s=600.0,
        ack_stale_s=2700.0,
        held_assign_watchdog_s=3.0,
    )
    clock._emitters.append(bored)
    bored.relay = relay
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)

    def write_outbox(text: str) -> bool:
        outbox.append(text)
        bored.on_outbox(text)
        return True

    relay.write_outbox = write_outbox
    # Force-hold regardless of harvest (simulate harvest already cleared).
    relay.hold_assigns_while = lambda: True
    relay.on_hold_assign = lambda line: bored.note_held_assign()

    st = relay.deliver("Jeeves", "#marchhare", ASSIGN_LINE)
    assert st == "held_until_turn_end"
    assert injected == []
    # Drop the hold so watchdog may inject (production: hold ended, assign still parked).
    relay.hold_assigns_while = lambda: False

    clock.advance(4.0)
    assert _wait(lambda: len(injected) >= 1, clock, timeout=4.0), (
        f"watchdog must inject ACKed held assign; injected={injected!r} logs={logs[-10:]!r}"
    )
    assert "bobiverse#5484" in injected[0].lower()
    bored.stop()
