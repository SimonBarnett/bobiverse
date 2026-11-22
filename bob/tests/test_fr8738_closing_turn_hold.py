"""FR #8738: no new job is delivered into the prior job's closing turn.

Seat log (marchhare-12400, 2026-11-21): done-miss armed for MRB #8672, the reminder
turn was still finishing #8672, Jeeves pushed MRB #8673, and the seat wrote
"DONE for #8672 and ACK for #8673" in one turn.

Pins:
* DONE A inside an open turn, then assign B: B stays parked (ACK on receipt only)
  across the whole open turn, past harvest_hold_s and past the FR #2834 !bored cap.
  It is injected only after that turn ends.
* No flush path (turn watcher, post_bored, harvest expiry, watchdog) injects B while
  the closing turn is open.
* The done-miss reminder turn counts as open even before the watcher reports
  turn_started, so DONE A in it does not skip the hold.
* done-miss !bored (GIVEUP no-terminal-reply) stays quiet while the reminder turn is
  visibly running; a dead reminder still gives up (FR #7352 parity).
* turn_ended with only a parked, ACKed-on-receipt B open is not a done-miss for B.
"""
from __future__ import annotations

import time

import bob_worker as bw

A_ACK = "ACK MRB SimonBarnett/bobiverse#8672"
A_DONE = "DONE MRB SimonBarnett/bobiverse#8672 PASS https://github.com/SimonBarnett/bobiverse/pull/8672"
B_ASSIGN = (
    "marchhare-12400: MRB SimonBarnett/bobiverse#8673 "
    "https://github.com/SimonBarnett/bobiverse/pull/8673"
)


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


def _settle(clock: FakeClock, secs: float = 0.15) -> None:
    """Let the emitter thread run without moving the fake clock much."""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        clock.advance(0.0)
        time.sleep(0.01)


class Rig:
    def __init__(self, **kw):
        self.clock = FakeClock(0.0)
        self.injected: list[str] = []
        self.outbox: list[str] = []
        self.logs: list[str] = []
        self.bored_sent: list[float] = []
        self.giveups: list[tuple[str, str]] = []
        self.reminds: list[str] = []
        self.relay = bw.Relay(log=self.logs.append, clock=self.clock, max_pending=8)
        self.relay.set_target(lambda line: self.injected.append(line) or True)
        kw.setdefault("harvest_hold_s", 90.0)
        kw.setdefault("turn_hold_max_s", 120.0)
        kw.setdefault("finish_turn_hold_max_s", 1800.0)
        kw.setdefault("done_miss_grace_s", 20.0)
        kw.setdefault("done_miss_reply_s", 30.0)
        kw.setdefault("ack_quiet_s", 60.0)
        kw.setdefault("held_assign_watchdog_s", 45.0)
        self.bored = bw.BoredEmitter(
            self._post_bored,
            self.logs.append,
            clock=self.clock,
            idle_s=99999.0,
            repeat_s=99999.0,
            retry_s=0.05,
            assign_grace_s=600.0,
            ack_stale_s=2700.0,
            **kw,
        )
        b = self.bored
        self.clock._emitters.append(b)
        b.relay = self.relay
        b.done_miss_remind_fn = self.reminds.append
        b.seat_release_giveup_fn = lambda key, why: self.giveups.append((key, why))
        self.relay.write_outbox = self._write_outbox
        # Production wiring (Supervisor): FR #2811 / #8246 / #8738.
        self.relay.hold_assigns_while = lambda: b.holding_incoming_assigns
        self.relay.on_hold_assign = lambda _line: b.note_held_assign()
        self.relay.turn_busy_other_job = b.live_turn_blocks_assign
        self.relay.defer_flush_while = lambda: b.closing_turn_open
        b.start()
        b.set_ready(True)
        assert _wait(lambda: any(r == "start" for _, r in b.sent), self.clock)

    def _write_outbox(self, text: str) -> bool:
        self.outbox.append(text)
        self.bored.on_outbox(text)
        return True

    def _post_bored(self) -> bool:
        # Same shape as Supervisor.post_bored: flush held assigns first.
        self.bored.clear_held_assign()
        n = self.relay.release_held_assigns()
        if n:
            self.bored.activity(mark_work=True)
            return False
        self.bored_sent.append(self.clock())
        return True

    def turn_ended_like_cursor(self) -> None:
        """Cursor watcher order: bored.turn_ended then relay.release_held_assigns."""
        self.bored.turn_ended()
        n = self.relay.release_held_assigns()
        if n:
            self.bored.activity(mark_work=True)
        self.bored.clear_held_assign()

    def reasons(self) -> list[str]:
        return [r for _, r in self.bored.sent]

    def stop(self) -> None:
        self.bored.stop()


def _b_injected(rig: Rig) -> bool:
    return any("bobiverse#8673" in x.lower() for x in rig.injected)


def test_fr8738_done_a_then_offer_b_held_across_open_turn():
    rig = Rig()
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(30.0)
    rig._write_outbox(A_DONE)  # agent writes DONE A mid-turn; turn still open
    assert b.closing_turn_open is True
    # Jeeves FR #3893 done-offer arrives while the DONE A turn is still open.
    st = rig.relay.deliver("Jeeves", "#marchhare", B_ASSIGN)
    assert st == "held_until_turn_end"
    assert any(x.startswith("ACK MRB SimonBarnett/bobiverse#8673") for x in rig.outbox)
    assert rig.injected == []
    # Past harvest_hold_s, the FR #2834 !bored cap and the held-assign watchdog:
    # the turn is still closing job A, so B must stay parked.
    for _ in range(6):
        rig.clock.advance(60.0)
        _settle(rig.clock, 0.05)
    assert rig.injected == [], rig.logs[-12:]
    assert rig.relay.has_pending_work() is True
    assert b.closing_turn_open is True
    # The turn that closed A ends: now (and only now) B is delivered.
    rig.turn_ended_like_cursor()
    assert _wait(lambda: _b_injected(rig), rig.clock), rig.logs[-12:]
    assert not any("done-miss armed" in m and "#8673" in m for m in rig.logs), rig.logs
    rig.stop()


def test_fr8738_no_flush_path_injects_into_closing_turn():
    """turn-watcher release, post_bored and watchdog all go through the Relay gate."""
    rig = Rig()
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(5.0)
    rig._write_outbox(A_DONE)
    assert rig.relay.deliver("Jeeves", "#marchhare", B_ASSIGN) == "held_until_turn_end"
    # Direct flush attempts while A's closing turn is open keep B parked.
    assert rig.relay.release_held_assigns() == 0
    assert rig._post_bored() is True or rig.injected == []
    assert rig.injected == []
    assert rig.relay.has_pending_work() is True
    assert any("closing turn still open (FR #8738)" in m for m in rig.logs), rig.logs
    # No same-turn DONE A + ACK B inject: nothing reached the agent before turn_ended.
    rig.clock.advance(200.0)
    _settle(rig.clock)
    assert rig.injected == []
    rig.turn_ended_like_cursor()
    assert _wait(lambda: _b_injected(rig), rig.clock)
    assert len([x for x in rig.injected if "#8673" in x]) == 1
    rig.stop()


def test_fr8738_reminder_turn_unseen_still_parks_next_assign():
    """done-miss reminder injected; watcher has not seen it start; DONE A lands."""
    rig = Rig()
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(170.0)
    b.turn_ended()
    assert any("done-miss armed" in m for m in rig.logs)
    rig.clock.advance(21.0)
    assert _wait(lambda: len(rig.reminds) == 1, rig.clock)
    # Reminder turn is running but no turn_started was reported (transcript lag).
    assert b.closing_turn_open is True
    rig.clock.advance(10.0)
    rig._write_outbox(A_DONE)
    assert not any("skip harvest hold (turn already ended)" in m for m in rig.logs[-4:])
    assert rig.relay.deliver("Jeeves", "#marchhare", B_ASSIGN) == "held_until_turn_end"
    for _ in range(4):
        rig.clock.advance(40.0)
        _settle(rig.clock, 0.05)
    assert rig.injected == [], rig.logs[-12:]
    rig.turn_ended_like_cursor()
    assert _wait(lambda: _b_injected(rig), rig.clock), rig.logs[-12:]
    rig.stop()


def test_fr8738_done_miss_bored_waits_while_reminder_turn_active():
    """Reminder turn visibly working (agent I/O) past done_miss_reply_s: no GIVEUP/!bored."""
    rig = Rig(done_miss_reply_s=30.0, ack_quiet_s=60.0)
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(100.0)
    b.turn_ended()
    rig.clock.advance(21.0)
    assert _wait(lambda: len(rig.reminds) == 1, rig.clock)
    for _ in range(6):
        rig.clock.advance(15.0)
        b.note_agent_active()
        _settle(rig.clock, 0.03)
    # 90 s after the reminder (> reply_s) with live agent I/O: still the job's turn.
    assert "done-miss" not in rig.reasons(), rig.logs[-10:]
    assert rig.giveups == []
    assert b.ack_open is True
    assert b.closing_turn_open is True
    # Agent goes quiet past ack_quiet_s: the reminder turn is dead, release as before.
    rig.clock.advance(61.0)
    assert _wait(lambda: "done-miss" in rig.reasons(), rig.clock), rig.logs[-10:]
    assert rig.giveups and rig.giveups[0][1] == "no-terminal-reply"
    assert b.closing_turn_open is False
    rig.stop()


def test_fr8738_dead_reminder_still_gives_up_after_reply_window():
    """FR #7352 parity: no turn and no agent I/O after the reminder -> GIVEUP + !bored."""
    rig = Rig(done_miss_reply_s=30.0)
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(100.0)
    b.turn_ended()
    rig.clock.advance(21.0)
    assert _wait(lambda: len(rig.reminds) == 1, rig.clock)
    rig.clock.advance(31.0)
    assert _wait(lambda: "done-miss" in rig.reasons(), rig.clock), rig.logs[-10:]
    assert rig.giveups[0] == ("MRB SimonBarnett/bobiverse#8672", "no-terminal-reply")
    rig.stop()


def test_fr8738_done_miss_does_not_stamp_second_job():
    """Parked, ACKed-on-receipt B is not the turn's job: turn_ended must not done-miss B."""
    rig = Rig()
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(5.0)
    rig._write_outbox(A_DONE)
    assert rig.relay.deliver("Jeeves", "#marchhare", B_ASSIGN) == "held_until_turn_end"
    rig.clock.advance(5.0)
    # Grok-style watcher: only bored.turn_ended (no direct relay flush).
    b.turn_ended()
    assert _wait(lambda: _b_injected(rig), rig.clock), rig.logs[-12:]
    assert not any("done-miss armed" in m for m in rig.logs), rig.logs
    assert rig.reminds == []
    assert rig.giveups == []
    # One assign delivered, no extra !bored that could fetch a third job.
    assert len([x for x in rig.injected if "#8673" in x]) == 1
    assert "done" not in rig.reasons()
    rig.stop()


def test_fr8738_closing_turn_safety_cap_releases_lost_turn_end():
    """A lost turn_ended cannot park B forever: finish_turn_hold_max_s drops the mark.

    Unseen reminder turn (no turn_started reported), DONE A, B parked. With no
    turn_ended ever, B is delivered once the closing-turn safety cap expires.
    """
    rig = Rig(finish_turn_hold_max_s=300.0, turn_hold_max_s=120.0)
    b = rig.bored
    b.turn_started()
    rig._write_outbox(A_ACK)
    rig.clock.advance(100.0)
    b.turn_ended()
    rig.clock.advance(21.0)
    assert _wait(lambda: len(rig.reminds) == 1, rig.clock)
    rig._write_outbox(A_DONE)
    assert rig.relay.deliver("Jeeves", "#marchhare", B_ASSIGN) == "held_until_turn_end"
    rig.clock.advance(250.0)
    _settle(rig.clock)
    assert rig.injected == [], rig.logs[-12:]
    rig.clock.advance(60.0)
    assert _wait(lambda: _b_injected(rig), rig.clock, timeout=4.0), rig.logs[-12:]
    assert any("safety net" in m for m in rig.logs)
    rig.stop()


def test_fr8738_supervisor_wires_defer_flush_gate():
    import inspect

    src = inspect.getsource(bw)
    assert "relay.defer_flush_while = lambda: bool(self.bored and self.bored.closing_turn_open)" in src
    assert "BOB_WORKER_FINISH_TURN_HOLD_MAX_S" in src
