"""FR #2802: !bored when grok turn ends; harvest_hold_s only as fallback."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

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


def test_fr2802_turn_end_releases_hold_before_fallback():
    """DONE at t=0, turn_ended at t=20 -> !bored reason=done by t=21, not t=90."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#2802")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#2802 https://example.com/p/1")
    n_after_done = len(sent)
    clock.advance(20.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: len(sent) > n_after_done, clock)
    assert e.sent[-1][1] == "done"
    assert e.sent[-1][0] < 90.0
    assert any("hold released" in m for m in logs)
    e.stop()


def test_fr2802_no_turn_end_uses_fallback_hold():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#1")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#1 https://example.com/p/1")
    n0 = len(sent)
    clock.advance(89.0)
    time.sleep(0.05)
    assert len(sent) == n0
    clock.advance(2.0)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    e.stop()


def test_fr2802_outbox_extends_fallback_when_no_turn_end():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#2")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#2 https://example.com/p/2")
    n0 = len(sent)
    clock.advance(60.0)
    e.on_outbox("PRIVMSG #m :harvest note")
    clock.advance(89.0)
    time.sleep(0.05)
    assert len(sent) == n0
    clock.advance(5.0)
    assert _wait(lambda: len(sent) > n0, clock, timeout=3.0)
    e.stop()


def test_fr2802_turn_end_with_ack_open_does_nothing():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#3")
    n0 = len(sent)
    clock.advance(5.0)
    e.turn_ended(at=clock())
    clock.advance(100.0)
    time.sleep(0.05)
    assert len(sent) == n0
    e.stop()


def test_fr2802_turn_end_with_inject_pending_blocked():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=0.0, assign_grace_s=600.0, idle_s=120.0)
    # start already sent; mark inject pending
    e.activity(mark_work=True)
    n0 = len(sent)
    clock.advance(5.0)
    e.turn_ended(at=clock())
    clock.advance(10.0)
    time.sleep(0.05)
    assert len(sent) == n0
    e.stop()


def test_fr2802_stale_turn_end_before_done_ignored():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#4")
    clock.advance(10.0)
    e.on_outbox("DONE FR o/r#4 https://example.com/p/4")
    n0 = len(sent)
    e.turn_ended(at=5.0)  # before DONE at t=10
    clock.advance(20.0)
    time.sleep(0.05)
    assert len(sent) == n0
    clock.advance(80.0)
    assert _wait(lambda: len(sent) > n0, clock)
    e.stop()


def test_fr2802_new_turn_cancels_until_next_turn_end():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0)
    e.on_outbox("ACK FR o/r#5")
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#5 https://example.com/p/5")
    n0 = len(sent)
    clock.advance(20.0)
    e.turn_ended(at=clock())
    e.turn_started(at=clock())
    clock.advance(2.0)
    time.sleep(0.05)
    assert len(sent) == n0, "turn_started after turn_ended must cancel pending !bored"
    clock.advance(5.0)
    e.turn_ended(at=clock())
    clock.advance(0.05)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "done"
    e.stop()


def test_fr2802_one_per_second_turn_reason():
    clock = FakeClock(100.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=0.0, idle_s=120.0)
    n0 = len(sent)
    e.turn_ended(at=clock())
    e.turn_ended(at=clock())
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "turn"
    n1 = len(sent)
    e.turn_ended(at=clock())
    clock.advance(0.2)
    time.sleep(0.05)
    assert len(sent) == n1
    e.stop()


def test_fr2802_watcher_fires_on_turn_ended(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    seen: list = []
    stop = threading.Event()

    def on_started(turn: int | None, wall: float) -> None:
        seen.append(("started", turn, wall))

    def on_ended(turn: int | None, wall: float) -> None:
        seen.append(("ended", turn, wall))

    w = bw.GrokTurnWatcher(
        events_path=events,
        on_turn_started=on_started,
        on_turn_ended=on_ended,
        stop_event=stop,
        poll_s=0.05,
        log=lambda m: None,
    )
    th = threading.Thread(target=w.run, name="test-turn-watch", daemon=True)
    th.start()
    time.sleep(0.08)
    with events.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": "2026-10-06T15:00:00.000Z",
                    "type": "turn_started",
                    "turn_number": 3,
                }
            )
            + "\n"
        )
        f.write("not-json\n")
        f.write(
            json.dumps({"ts": "2026-10-06T15:00:10.000Z", "type": "tool_call", "name": "x"})
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "ts": "2026-10-06T15:00:20.000Z",
                    "type": "turn_ended",
                    "outcome": "completed",
                }
            )
            + "\n"
        )
        f.flush()
    assert _wait(lambda: any(x[0] == "ended" for x in seen), FakeClock(), timeout=2.0, step=0)
    # FakeClock unused; plain sleep wait:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not any(x[0] == "ended" for x in seen):
        time.sleep(0.05)
    stop.set()
    th.join(timeout=2.0)
    kinds = [x[0] for x in seen]
    assert kinds.count("started") == 1
    assert kinds.count("ended") == 1


def test_fr2802_watcher_follows_session_switch(tmp_path: Path):
    a = tmp_path / "a" / "events.jsonl"
    b = tmp_path / "b" / "events.jsonl"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("", encoding="utf-8")
    b.write_text("", encoding="utf-8")
    cur = {"path": a}
    ended: list = []
    stop = threading.Event()

    w = bw.GrokTurnWatcher(
        events_path_fn=lambda: cur["path"],
        on_turn_started=lambda *a, **k: None,
        on_turn_ended=lambda turn, wall: ended.append(wall),
        stop_event=stop,
        poll_s=0.05,
        log=lambda m: None,
    )
    th = threading.Thread(target=w.run, daemon=True)
    th.start()
    time.sleep(0.08)
    with a.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-10-06T15:01:00.000Z", "type": "turn_ended"}) + "\n")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(ended) < 1:
        time.sleep(0.05)
    assert len(ended) == 1
    cur["path"] = b
    time.sleep(0.15)
    with b.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-10-06T15:02:00.000Z", "type": "turn_ended"}) + "\n")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(ended) < 2:
        time.sleep(0.05)
    stop.set()
    th.join(timeout=2.0)
    assert len(ended) == 2


def test_fr2802_opt_out_and_non_grok_skip_watcher(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "0")
    assert bw.bored_on_turn_end_enabled() is False
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "1")
    assert bw.bored_on_turn_end_enabled() is True
    assert bw.should_start_turn_watcher("grok") is True
    assert bw.should_start_turn_watcher("cursor") is False
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "0")
    assert bw.should_start_turn_watcher("grok") is False
