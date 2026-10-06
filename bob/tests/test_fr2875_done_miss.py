"""FR #2875: turn_ended with ACK open and no DONE/NACK/GIVEUP -> done-miss remind then release."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_turn_ended_with_open_ack_no_done_arms_done_miss_and_logs():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.on_outbox("ACK MRB o/r#2856")
    clock.advance(171.0)
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs), logs
    assert any("o/r#2856" in m and "done-miss armed" in m for m in logs)
    assert e.ack_open is True
    assert len([r for _, r in e.sent if r == "done-miss"]) == 0
    e.stop()


def test_done_miss_reminder_injected_once_after_grace(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(
        bw.done_miss_reminder_line(shop="#marchhare", outbox=tmp_path / "outbox.txt", job_key=key)
    )
    e.on_outbox("ACK MRB o/r#2856")
    clock.advance(171.0)
    e.turn_ended(at=clock())
    clock.advance(19.0)
    time.sleep(0.05)
    assert reminds == []
    clock.advance(2.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    line = reminds[0]
    assert line.startswith("FROM bob-worker #marchhare ")
    assert "o/r#2856" in line
    assert str(tmp_path / "outbox.txt") in line
    assert "do not check the outbox first" in line.lower() or "drained and always empty" in line
    clock.advance(60.0)
    clock.advance(600.0)
    time.sleep(0.05)
    assert len(reminds) == 1
    assert any("done-miss: reminder injected" in m for m in logs)
    e.stop()


def test_turn_started_within_grace_cancels_reminder(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB o/r#1")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    clock.advance(5.0)
    e.turn_started(at=clock())
    clock.advance(30.0)
    time.sleep(0.05)
    assert reminds == []
    e.stop()


def test_matching_done_after_reminder_follows_harvest_hold_then_turn_end_bored(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB o/r#2856")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: len(reminds) == 1, clock, timeout=5.0) or (
        clock.advance(20.0) or _wait(lambda: len(reminds) == 1, clock)
    )
    clock.advance(25.0)
    assert _wait(lambda: len(reminds) >= 1, clock)
    e.turn_started(at=clock())
    clock.advance(1.0)
    n0 = len(sent)
    e.on_outbox("DONE MRB o/r#2856 FAIL https://example.com/p/2856")
    clock.advance(1.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in e.sent[n0:]), clock)
    assert not any(r == "done-miss" for _, r in e.sent)
    e.stop()


def test_done_for_other_key_does_not_clear_done_miss(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB o/r#2856")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    clock.advance(5.0)
    e.on_outbox("DONE FR o/r#9 https://example.com/p/9")
    assert e.ack_open is True
    clock.advance(20.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    assert reminds[0] == "MRB o/r#2856"
    e.stop()


def test_second_turn_end_without_done_releases_seat_once(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB o/r#2856")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    e.turn_started(at=clock())
    clock.advance(5.0)
    n0 = len(sent)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent[n0:]), clock)
    assert len([r for _, r in e.sent if r == "done-miss"]) == 1
    assert e.ack_open is False
    assert any("still no DONE" in m and "releasing seat" in m for m in logs)
    clock.advance(30.0)
    time.sleep(0.05)
    assert len([r for _, r in e.sent if r == "done-miss"]) == 1
    e.stop()


def test_no_done_miss_while_inject_pending_or_mid_turn(tmp_path: Path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0, assign_grace_s=600.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    # Mid-turn: turn_started without turn_ended — turn_ended path not called.
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#1")
    clock.advance(5.0)
    assert not any("done-miss armed" in m for m in logs)
    # Inject-pending without ACK: turn_ended should not arm done-miss.
    e2, sent2, logs2 = _emitter(FakeClock(0.0), harvest_hold_s=90.0, done_miss_grace_s=20.0, assign_grace_s=600.0)
    e2.done_miss_remind_fn = lambda key: reminds.append(key)
    e2.activity(mark_work=True)
    e2.turn_ended(at=e2.clock())
    assert not any("done-miss armed" in m for m in logs2)
    clock.advance(30.0)
    e.stop()
    e2.stop()


def test_replay_29256_timeline(tmp_path: Path):
    """ACK 18:13:02, turn_ended 18:15:53 (~171s later); remind by +20; free after next turn end."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0, ack_stale_s=2700.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#2856")
    t_ack = clock()
    clock.advance(171.0)  # ~18:15:53 - 18:13:02
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs)
    clock.advance(20.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    assert clock() - t_ack < 200.0
    e.turn_started(at=clock())
    clock.advance(30.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock)
    first_bored_done_miss = next(t for t, r in e.sent if r == "done-miss")
    assert first_bored_done_miss < 2700.0
    e.stop()


def test_ack_stale_s_fallback_unchanged():
    """No turn signal: seat still frees via ack_stale_s (non-grok path)."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0, ack_stale_s=60.0, idle_s=5.0, repeat_s=5.0)
    e.on_outbox("ACK MRB o/r#1")
    n0 = len(sent)
    clock.advance(61.0)
    assert _wait(lambda: len(sent) > n0 and any(r == "idle" for _, r in e.sent[n0:]), clock, timeout=5.0)
    assert not any("done-miss armed" in m for m in logs)
    e.stop()


def test_done_miss_reminder_line_shape(tmp_path: Path):
    line = bw.done_miss_reminder_line(
        shop="#marchhare",
        outbox=tmp_path / "outbox.txt",
        job_key="MRB o/r#2856",
    )
    assert line.startswith("FROM bob-worker #marchhare ")
    assert "MRB o/r#2856" in line
    assert "BOB_OUTBOX" in line
    assert "[outbox:" in line