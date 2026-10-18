"""FR #4670: Cursor mid-tool quiet must not false-fire turn_ended / done-miss release."""
from __future__ import annotations

import os
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def _chat(root, name="chat1", born=None):
    d = root / "ws" / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "store.db"
    f.write_bytes(b"x")
    if born is not None:
        os.utime(f, (born, born))
    return d


def _touch(d, t):
    f = d / "store.db-wal"
    f.write_bytes(b"y")
    os.utime(f, (t, t))


def test_cursor_ack_open_uses_longer_quiet_before_turn_ended(tmp_path, monkeypatch):
    """Acceptance: multi-tool gaps under ack_quiet_s produce no turn_ended."""
    monkeypatch.delenv("BOB_WORKER_CURSOR_ACK_QUIET_S", raising=False)
    t0 = time.time()
    d = _chat(tmp_path, born=t0)
    now = [t0 + 1]
    ack = {"open": True}
    ev = []
    w = bw.CursorTurnWatcher(
        since_wall=t0,
        chats_root=tmp_path,
        quiet_s=20,
        ack_quiet_s=180,
        ack_open_fn=lambda: bool(ack["open"]),
        clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)),
        on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() == "started"
    # Tool gap of 90 s while ACK open — must stay mid-turn.
    now[0] = t0 + 90
    assert w.tick() is None
    assert ev == [("s", 1)]
    # Still under ack_quiet_s.
    now[0] = t0 + 170
    assert w.tick() is None
    # Past ack_quiet_s — real idle while ACK open may end.
    now[0] = t0 + 182
    assert w.tick() == "ended"
    assert ev == [("s", 1), ("e", 1)]
    # After ACK clears, short quiet_s applies again.
    ack["open"] = False
    _touch(d, t0 + 200)
    now[0] = t0 + 201
    assert w.tick() == "started"
    now[0] = t0 + 222
    assert w.tick() == "ended"


def test_cursor_no_ack_keeps_short_quiet(tmp_path):
    t0 = time.time()
    _chat(tmp_path, born=t0)
    now = [t0 + 1]
    ev = []
    w = bw.CursorTurnWatcher(
        since_wall=t0,
        chats_root=tmp_path,
        quiet_s=20,
        ack_quiet_s=180,
        ack_open_fn=lambda: False,
        clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)),
        on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() == "started"
    now[0] = t0 + 26
    assert w.tick() == "ended"


def test_done_miss_release_requires_post_remind_turn_started(tmp_path: Path):
    """Acceptance: after reminder, a bare turn_ended without turn_started must not release."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK FR o/r#4670")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    n0 = len(sent)
    # False mid-turn end after reminder, no new turn_started — stay busy.
    e.turn_ended(at=clock())
    clock.advance(1.0)
    time.sleep(0.05)
    assert not any(r == "done-miss" for _, r in e.sent[n0:])
    assert e.ack_open is True
    assert any("awaiting reminder turn" in m for m in logs) or any(
        "post-remind" in m for m in logs
    )
    # Reminder turn starts then ends without DONE — now release.
    e.turn_started(at=clock())
    clock.advance(2.0)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent[n0:]), clock)
    assert e.ack_open is False
    e.stop()


def test_ack_quiet_env_clamped(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_CURSOR_ACK_QUIET_S", "10")
    assert bw._cursor_turn_ack_quiet_s() == 60.0
    monkeypatch.setenv("BOB_WORKER_CURSOR_ACK_QUIET_S", "9999")
    assert bw._cursor_turn_ack_quiet_s() == 900.0
    monkeypatch.delenv("BOB_WORKER_CURSOR_ACK_QUIET_S")
    assert bw._cursor_turn_ack_quiet_s() == 180.0
