"""FR #4670: Cursor tool gaps must not arm done-miss or !bored; release waits for the reminder turn."""
from __future__ import annotations

import os
import time

import bob_worker as bw
from test_cursor_turn_watcher import _arm_transcript, _chat, _text_line, _tool_line, _touch, _user_line
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_tool_turn_skips_reminder_and_release_waits_for_reminder_turn(tmp_path):
    clock = FakeClock(time.time())
    e, _sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    reminds: list[str] = []
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK FR SimonBarnett/bobiverse#4670")
    n_busy = len(e.sent)
    t0 = clock()
    d = _chat(tmp_path, born=t0)
    projects = tmp_path / "projects"
    path = _arm_transcript(d, projects, [_tool_line()])
    os.utime(path, (t0, t0))
    w = bw.CursorTurnWatcher(
        since_wall=t0 - 1,
        chats_root=tmp_path,
        projects_root=projects,
        quiet_s=20,
        clock=clock,
        on_turn_started=lambda n, t: e.turn_started(at=t, turn=n),
        on_turn_ended=lambda n, t: e.turn_ended(at=t, turn=n),
    )
    assert w.tick() == "started"
    clock.advance(300)
    assert w.tick() is None
    assert e.ack_open is True
    assert len(e.sent) == n_busy
    assert not any("done-miss" in m for m in logs)

    path.write_text(_tool_line() + "\n" + _text_line() + "\n", encoding="utf-8")
    clock.advance(1)
    os.utime(path, (clock(), clock()))
    _touch(d, clock())
    assert w.tick() is None
    clock.advance(21)
    assert w.tick() == "ended"
    assert any("done-miss armed" in m for m in logs)
    clock.advance(21)
    assert _wait(lambda: len(reminds) == 1, clock)
    assert e.ack_open is True
    assert not any(r == "done-miss" for _, r in e.sent)

    path.write_text(
        path.read_text(encoding="utf-8") + _user_line() + "\n" + _tool_line() + "\n",
        encoding="utf-8",
    )
    clock.advance(1)
    os.utime(path, (clock(), clock()))
    assert w.tick() == "started"
    clock.advance(300)
    assert w.tick() is None
    assert e.ack_open is True
    assert not any(r == "done-miss" for _, r in e.sent)

    path.write_text(path.read_text(encoding="utf-8") + _text_line("no done") + "\n", encoding="utf-8")
    clock.advance(1)
    os.utime(path, (clock(), clock()))
    assert w.tick() is None
    clock.advance(21)
    assert w.tick() == "ended"
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock)
    assert e.ack_open is False
    assert any("still no DONE" in m and "releasing seat" in m for m in logs)
    e.stop()
