"""Cursor seats: infer turn end from the chat store so held assigns release without the 600 s fallback."""
from __future__ import annotations

import os
import time

import bob_worker as bw


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


def test_should_start_cursor_turn_watcher(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_CURSOR_TURN_WATCH", raising=False)
    monkeypatch.delenv("BOB_WORKER_BORED_ON_TURN_END", raising=False)
    assert bw.should_start_cursor_turn_watcher("cursor") is True
    assert bw.should_start_cursor_turn_watcher("grok") is False
    monkeypatch.setenv("BOB_WORKER_CURSOR_TURN_WATCH", "0")
    assert bw.should_start_cursor_turn_watcher("cursor") is False


def test_turn_started_then_ended_after_quiet(tmp_path):
    t0 = time.time()
    d = _chat(tmp_path, born=t0)
    now = [t0 + 1]
    ev = []
    w = bw.CursorTurnWatcher(
        since_wall=t0, chats_root=tmp_path, quiet_s=20, clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)), on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() == "started"
    _touch(d, t0 + 5); now[0] = t0 + 6
    assert w.tick() is None            # still active
    now[0] = t0 + 20
    assert w.tick() is None            # 15 s quiet < 20
    now[0] = t0 + 26
    assert w.tick() == "ended"
    now[0] = t0 + 60
    assert w.tick() is None            # fires once per turn
    _touch(d, t0 + 61); now[0] = t0 + 62
    assert w.tick() == "started"
    assert ev == [("s", 1), ("e", 1), ("s", 2)]


def test_ignores_chats_older_than_spawn(tmp_path):
    t0 = time.time()
    _chat(tmp_path, "old", born=t0 - 3600)
    w = bw.CursorTurnWatcher(since_wall=t0, chats_root=tmp_path, quiet_s=5, clock=lambda: t0 + 100)
    assert w.tick() is None and w.chat_dir is None


def test_binds_chat_created_after_spawn(tmp_path):
    t0 = time.time()
    _chat(tmp_path, "old", born=t0 - 3600)
    new = _chat(tmp_path, "new", born=t0 + 3)
    w = bw.CursorTurnWatcher(since_wall=t0, chats_root=tmp_path, quiet_s=5, clock=lambda: t0 + 4)
    w.tick()
    assert w.chat_dir == new


def test_quiet_env_clamped(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_CURSOR_TURN_QUIET_S", "1")
    assert bw._cursor_turn_quiet_s() == 5.0
    monkeypatch.delenv("BOB_WORKER_CURSOR_TURN_QUIET_S")
    assert bw._cursor_turn_quiet_s() == 20.0
