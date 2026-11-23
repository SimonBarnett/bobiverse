"""FR #9365: after harvest clears, skip the first idle_s quiet before !bored."""
from __future__ import annotations

import time

import bob_worker as bw


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)
        self._emitters: list = []

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)
        for e in self._emitters:
            with e._cv:
                e._cv.notify_all()


def _wait(pred, clock: FakeClock, timeout: float = 2.0, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        clock.advance(step)
        time.sleep(0.005)
    return pred()


def _emitter(clock: FakeClock, **kw):
    sent: list = []
    logs: list = []
    kw.setdefault("idle_s", 120.0)
    kw.setdefault("repeat_s", 180.0)
    kw.setdefault("ack_stale_s", 2700.0)
    kw.setdefault("harvest_hold_s", 90.0)
    kw.setdefault("assign_grace_s", 600.0)
    kw["clock"] = clock
    e = bw.BoredEmitter(lambda: sent.append(clock()) or True, logs.append, **kw)
    clock._emitters.append(e)
    e.start()
    e.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in e.sent), clock)
    return e, sent, logs


def test_fr9365_post_harvest_idle_within_seconds_not_idle_s():
    """DONE + turn_ended -> done !bored, then idle !bored by ~t+5, not t+120."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, idle_s=120.0)
    e.turn_started(at=clock())
    e.on_outbox("ACK FR o/r#9365")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#9365 https://example.com/p/9365")
    clock.advance(1.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in e.sent), clock)
    t_done = e.sent[-1][0]
    # Harvest chatter must not push the next idle out by another 120s.
    e.on_outbox("PRIVMSG #redqueen :harvest note")
    clock.advance(3.0)
    assert _wait(lambda: any(r == "idle" for _, r in e.sent), clock, timeout=3.0)
    t_idle = next(t for t, r in e.sent if r == "idle")
    assert t_idle - t_done < 30.0, (t_done, t_idle, e.sent)
    assert any("post-harvest" in m for m in logs) or any(
        "reason=idle" in m and "post-harvest" in m for m in logs
    )
    e.stop()


def test_fr9365_harvest_chatter_does_not_reset_idle_when_skip_armed():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=0.0, idle_s=120.0)
    e.on_outbox("ACK FR o/r#1")
    clock.advance(0.5)
    e.on_outbox("GIVEUP FR o/r#1")
    assert _wait(lambda: any(r == "free" for _, r in e.sent), clock)
    assert e._post_harvest_skip_idle is True
    before = e._idle_since
    e.on_outbox("PRIVMSG #m :more harvest")
    assert e._idle_since == before
    e.stop()


def test_fr9365_second_idle_uses_normal_idle_s():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=0.0, idle_s=5.0, repeat_s=5.0)
    e.on_outbox("ACK FR o/r#2")
    clock.advance(0.2)
    e.on_outbox("DONE FR o/r#2 https://example.com/p/2")
    assert _wait(lambda: any(r == "done" for _, r in e.sent), clock)
    assert _wait(lambda: sum(1 for _, r in e.sent if r == "idle") >= 1, clock)
    n_idle = sum(1 for _, r in e.sent if r == "idle")
    clock.advance(2.0)
    time.sleep(0.05)
    assert sum(1 for _, r in e.sent if r == "idle") == n_idle
    clock.advance(4.0)
    assert _wait(lambda: sum(1 for _, r in e.sent if r == "idle") > n_idle, clock)
    e.stop()
