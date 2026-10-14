"""FR #4259: repeat DONE after turn_ended must not re-arm harvest / leave a
permanently held assign; harvest wait expiry with no open turn releases held
assigns so !bored can fire again.
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


def _wait(pred, clock: FakeClock, timeout: float = 2.0, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        clock.advance(step)
        time.sleep(0.005)
    return pred()


DONE_LINE = "DONE FR SimonBarnett/bobiverse#1 https://github.com/SimonBarnett/bobiverse/pull/1"
ASSIGN_LINE = (
    "marchhare-1: FR SimonBarnett/bobiverse#9 "
    "https://github.com/SimonBarnett/bobiverse/issues/9"
)


def test_fr4259_repeat_done_after_turn_ended_does_not_rearm_harvest():
    """After DONE + turn_ended + !bored, a repeat DONE must not start a new harvest hold."""
    clock = FakeClock(0.0)
    sent: list = []
    logs: list = []
    bored = bw.BoredEmitter(
        lambda: sent.append(clock()) or True,
        logs.append,
        clock=clock,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )
    clock._emitters.append(bored)
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)

    bored.on_outbox(DONE_LINE)
    assert bored.holding_incoming_assigns is True
    clock.advance(5.0)
    bored.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in bored.sent), clock)
    assert bored.holding_incoming_assigns is False

    # Repeat identical DONE after turn_ended / !bored — must not re-arm.
    bored.on_outbox(DONE_LINE)
    assert bored.holding_incoming_assigns is False, (
        "repeat DONE after turn_ended must not re-arm harvest hold"
    )
    with bored._cv:
        assert bored._harvest_until is None, "harvest_until must stay cleared"
    bored.stop()


def test_fr4259_harvest_expiry_releases_held_assign_and_allows_bored():
    """Held assign parked during a re-armed (or expired) harvest with no open turn
    must be released when the wait expires so the seat can !bored again (or take the job).
    """
    clock = FakeClock(0.0)
    injected: list[str] = []
    bored_sent: list = []
    logs: list = []
    relay = bw.Relay(log=lambda m: None, clock=clock, max_pending=8)
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
        idle_s=2.0,
        repeat_s=2.0,
        retry_s=0.05,
        assign_grace_s=600.0,
    )
    clock._emitters.append(bored)
    bored.relay = relay
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)

    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    relay.on_hold_assign = lambda line: bored.note_held_assign()

    # First DONE + turn_ended + !bored (normal path).
    bored.on_outbox(DONE_LINE)
    clock.advance(1.0)
    bored.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in bored.sent), clock)
    n_after_done = len(bored_sent)

    # Simulate the bug: force a harvest re-arm as if a repeat DONE slipped through,
    # then park an assign while holding. (Production fix also blocks the re-arm;
    # this test covers the expiry-flush safety net.)
    with bored._cv:
        bored._begin_harvest_hold(clock())
        bored._held_assign = True
        bored._cv.notify_all()
    assert bored.holding_incoming_assigns is True

    st = relay.deliver("Jeeves", "#marchhare", ASSIGN_LINE)
    assert st == "held_until_turn_end"
    assert injected == []
    assert relay.has_pending_work() is True

    # Wait past harvest_hold_s with no turn open — must flush held assign.
    clock.advance(6.0)
    assert _wait(
        lambda: len(injected) >= 1 or len(bored_sent) > n_after_done,
        clock,
        timeout=3.0,
    )

    # Held job delivered (preferred). Must not stay permanently busy undelivered.
    assert len(injected) >= 1, "harvest expiry must release the held assign"
    assert "bobiverse#9" in injected[0].lower()
    assert relay.has_pending_work() is False
    with bored._cv:
        assert bored._held_assign is False
    bored.stop()


def test_fr4259_idle_bored_after_expiry_when_only_held_flag():
    """Harvest re-arm with _held_assign but no parked relay line: expiry clears the
    flag and the seat !bored again once idle."""
    clock = FakeClock(0.0)
    sent: list = []
    logs: list = []
    bored = bw.BoredEmitter(
        lambda: sent.append((clock(), "bored")) or True,
        logs.append,
        clock=clock,
        harvest_hold_s=3.0,
        idle_s=1.0,
        repeat_s=1.0,
        retry_s=0.05,
    )
    clock._emitters.append(bored)
    bored.start()
    bored.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in bored.sent), clock)

    bored.on_outbox(DONE_LINE)
    clock.advance(0.5)
    bored.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in bored.sent), clock)
    n_after = len(bored.sent)

    with bored._cv:
        bored._begin_harvest_hold(clock())
        bored._held_assign = True
        bored._cv.notify_all()

    clock.advance(4.0)
    assert _wait(lambda: len(bored.sent) > n_after, clock, timeout=3.0)
    assert any(r == "idle" for _, r in bored.sent[n_after:]), bored.sent[n_after:]
    with bored._cv:
        assert bored._held_assign is False
    bored.stop()
