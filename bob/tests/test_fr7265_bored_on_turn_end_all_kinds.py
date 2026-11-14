"""FR #7265: !bored at turn end for every seat kind; harvest_hold_s is fallback only."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

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


def _emitter(clock: FakeClock, kind: str = "grok", **kw):
    sent: list = []
    logs: list = []
    kw.setdefault("idle_s", 120.0)
    kw.setdefault("repeat_s", 180.0)
    kw.setdefault("ack_stale_s", 2700.0)
    kw.setdefault("harvest_hold_s", 90.0)
    kw.setdefault("assign_grace_s", 600.0)
    kw["clock"] = clock
    e = bw.BoredEmitter(lambda: sent.append(clock()) or True, logs.append, **kw)
    e.kind = kind
    clock._emitters.append(e)
    e.start()
    e.set_ready(True)
    assert _wait(lambda: any(r == "start" for _, r in e.sent), clock)
    return e, sent, logs


@pytest.mark.parametrize("kind", ["grok", "cursor", "opencode", "aider"])
def test_fr7265_done_after_turn_ended_skips_harvest_hold(kind):
    """DONE after the agent turn already ended → !bored within 5s, no 90s wait."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, kind=kind, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#7265")
    clock.advance(1.0)
    e.turn_started(at=clock(), turn=1)
    clock.advance(2.0)
    e.turn_ended(at=clock(), turn=1)
    n0 = len(sent)
    clock.advance(0.2)
    e.on_outbox("DONE FR o/r#7265 https://example.com/p/7265")
    assert _wait(lambda: len(sent) > n0, clock, timeout=2.0)
    assert e.sent[-1][1] == "done"
    assert e.sent[-1][0] < 10.0
    assert any("skip harvest hold" in m for m in logs)
    assert any("kind=%s" % kind in m and "trigger=turn_ended" in m for m in logs)
    assert not any("fallback timer, no turn_ended seen" in m for m in logs)
    e.stop()


@pytest.mark.parametrize("kind", ["grok", "cursor", "opencode", "aider"])
def test_fr7265_open_turn_waits_for_turn_ended_not_clock(kind):
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, kind=kind, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#7265")
    clock.advance(1.0)
    e.turn_started(at=clock(), turn=1)
    n0 = len(sent)
    e.on_outbox("DONE FR o/r#7265 https://example.com/p/7265")
    clock.advance(20.0)
    time.sleep(0.05)
    assert len(sent) == n0
    e.turn_ended(at=clock(), turn=1)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    assert e.sent[-1][0] < 90.0
    assert any("hold released" in m for m in logs)
    assert not any("fallback timer, no turn_ended seen" in m for m in logs)
    e.stop()


def test_fr7265_fallback_timer_logs_when_no_turn_ended():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, kind="grok", harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#7265")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#7265 https://example.com/p/7265")
    n0 = len(sent)
    clock.advance(91.0)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    assert any("fallback timer, no turn_ended seen" in m for m in logs)
    assert any("trigger=fallback-timer" in m for m in logs)
    e.stop()


def test_fr7265_no_bored_while_ack_open():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, kind="cursor")
    e.on_outbox("ACK FR o/r#7265")
    n0 = len(sent)
    e.turn_started(at=clock(), turn=1)
    clock.advance(1.0)
    e.turn_ended(at=clock(), turn=1)
    clock.advance(5.0)
    time.sleep(0.05)
    assert len(sent) == n0
    assert any("done-miss armed" in m for m in logs)
    e.stop()


def test_fr7265_one_bored_per_turn_end():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, kind="opencode")
    e.on_outbox("ACK FR o/r#7265")
    clock.advance(1.0)
    e.turn_started(at=clock(), turn=1)
    clock.advance(1.0)
    e.turn_ended(at=clock(), turn=1)
    e.on_outbox("DONE FR o/r#7265 https://example.com/p/7265")
    assert _wait(lambda: any(r == "done" for _, r in e.sent), clock)
    n_done = sum(1 for _, r in e.sent if r == "done")
    e.turn_ended(at=clock(), turn=1)
    clock.advance(2.0)
    time.sleep(0.05)
    assert sum(1 for _, r in e.sent if r == "done") == n_done
    e.stop()


def test_fr7265_should_start_aider_turn_watcher(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_AIDER_TURN_WATCH", raising=False)
    monkeypatch.delenv("BOB_WORKER_BORED_ON_TURN_END", raising=False)
    assert bw.should_start_aider_turn_watcher("aider") is True
    assert bw.should_start_aider_turn_watcher("grok") is False
    monkeypatch.setenv("BOB_WORKER_AIDER_TURN_WATCH", "0")
    assert bw.should_start_aider_turn_watcher("aider") is False


def test_fr7265_proc_idle_turn_watcher_started_then_ended():
    now = [0.0]
    activity = [0]
    ev = []

    def probe():
        return SimpleNamespace(activity=activity[0])

    w = bw.ProcIdleTurnWatcher(
        probe=probe,
        quiet_s=5.0,
        clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)),
        on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() is None
    activity[0] = 3
    now[0] = 1.0
    assert w.tick() == "started"
    now[0] = 2.0
    assert w.tick() is None
    activity[0] = 0
    now[0] = 3.0
    assert w.tick() is None
    now[0] = 7.5
    assert w.tick() is None
    now[0] = 8.1
    assert w.tick() == "ended"
    now[0] = 20.0
    assert w.tick() is None
    assert ev == [("s", 1), ("e", 1)]
