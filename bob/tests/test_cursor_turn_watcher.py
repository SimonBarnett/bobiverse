"""Cursor seats: infer turn end from the chat store so held assigns release without the 600 s fallback.

FR #4670: a quiet store during a tool call is not turn_ended. The agent transcript
(final assistant text, no pending tool_use) is the end signal.
"""
from __future__ import annotations

import json
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


def _arm_transcript(chat_dir, projects, lines, cwd=r"C:\ai\bob\worker"):
    (chat_dir / "meta.json").write_text(json.dumps({"cwd": cwd}), encoding="utf-8")
    slug = bw.cursor_project_slug(cwd)
    dest = projects / slug / "agent-transcripts" / chat_dir.name / f"{chat_dir.name}.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def _tool_line():
    return json.dumps({
        "role": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Shell", "input": {}}]},
    })


def _text_line(text="finished"):
    return json.dumps({
        "role": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    })


def _user_line(text="reminder"):
    return json.dumps({
        "role": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    })


def test_project_slug_matches_cursor_projects_dir():
    assert bw.cursor_project_slug(r"C:\ai\bob\worker") == "C-ai-bob-worker"


def test_tool_gap_several_minutes_does_not_end(tmp_path):
    """Acceptance: multi-tool turn with no final text never emits turn_ended."""
    t0 = time.time()
    d = _chat(tmp_path, born=t0)
    projects = tmp_path / "projects"
    _arm_transcript(d, projects, [_tool_line()])
    now = [t0 + 1]
    ev = []
    w = bw.CursorTurnWatcher(
        since_wall=t0, chats_root=tmp_path, projects_root=projects, quiet_s=20,
        clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)),
        on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() == "started"
    now[0] = t0 + 600
    assert w.tick() is None
    assert w._active is True
    assert ev == [("s", 1)]


def test_final_assistant_text_then_quiet_ends_once(tmp_path):
    t0 = time.time()
    d = _chat(tmp_path, born=t0)
    projects = tmp_path / "projects"
    path = _arm_transcript(d, projects, [_tool_line()])
    now = [t0 + 1]
    ev = []
    w = bw.CursorTurnWatcher(
        since_wall=t0, chats_root=tmp_path, projects_root=projects, quiet_s=20,
        clock=lambda: now[0],
        on_turn_started=lambda n, t: ev.append(("s", n)),
        on_turn_ended=lambda n, t: ev.append(("e", n)),
    )
    assert w.tick() == "started"
    now[0] = t0 + 400
    assert w.tick() is None
    path.write_text(_tool_line() + "\n" + _text_line() + "\n", encoding="utf-8")
    os.utime(path, (t0 + 401, t0 + 401))
    now[0] = t0 + 402
    assert w.tick() is None
    now[0] = t0 + 430
    assert w.tick() == "ended"
    now[0] = t0 + 800
    assert w.tick() is None
    assert ev == [("s", 1), ("e", 1)]


def test_user_line_keeps_turn_open(tmp_path):
    t0 = time.time()
    d = _chat(tmp_path, born=t0)
    projects = tmp_path / "projects"
    _arm_transcript(d, projects, [_text_line(), _user_line()])
    now = [t0 + 1]
    w = bw.CursorTurnWatcher(
        since_wall=t0, chats_root=tmp_path, projects_root=projects, quiet_s=20,
        clock=lambda: now[0],
    )
    assert w.tick() == "started"
    now[0] = t0 + 120
    assert w.tick() is None
    assert w._active is True


def test_quiet_env_clamped(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_CURSOR_TURN_QUIET_S", "1")
    assert bw._cursor_turn_quiet_s() == 5.0
    monkeypatch.delenv("BOB_WORKER_CURSOR_TURN_QUIET_S")
    assert bw._cursor_turn_quiet_s() == 20.0
