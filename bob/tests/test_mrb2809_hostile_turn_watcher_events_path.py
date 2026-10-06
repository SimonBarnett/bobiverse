"""MRB #2809 hostile: Supervisor turn watcher must tail events.jsonl, not the session dir."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_mrb2809_start_turn_watcher_path_fn_returns_events_jsonl():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    i = src.index("def _start_turn_watcher")
    chunk = src[i : i + 1200]
    path_fn = chunk[chunk.index("def _path") : chunk.index("def _on_started")]
    assert "grok_session_dir" in path_fn
    assert 'd / "events.jsonl"' in path_fn or "d / 'events.jsonl'" in path_fn
    assert "return grok_session_dir(cwd, sid or \"\")" not in path_fn


def test_mrb2809_grok_turn_watcher_requires_file_not_dir(tmp_path: Path):
    """Directory-only path never fires (pre-fix bug mode); events.jsonl file does."""
    sess = tmp_path / "sess"
    sess.mkdir()
    events = sess / "events.jsonl"
    events.write_text("", encoding="utf-8")
    ended: list = []
    stop = __import__("threading").Event()

    # Dir path: no fire
    w_dir = bw.GrokTurnWatcher(
        events_path=sess,
        on_turn_ended=lambda turn, wall: ended.append("dir"),
        stop_event=stop,
        poll_s=0.05,
    )
    th = __import__("threading").Thread(target=w_dir.run, daemon=True)
    th.start()
    __import__("time").sleep(0.12)
    with events.open("a", encoding="utf-8") as f:
        f.write('{"ts":"2026-10-06T16:00:00.000Z","type":"turn_ended"}\n')
        f.flush()
    __import__("time").sleep(0.2)
    stop.set()
    th.join(timeout=2.0)
    assert ended == []

    # File path: fires
    stop2 = __import__("threading").Event()
    ended2: list = []
    w_file = bw.GrokTurnWatcher(
        events_path=events,
        on_turn_ended=lambda turn, wall: ended2.append("file"),
        stop_event=stop2,
        poll_s=0.05,
    )
    th2 = __import__("threading").Thread(target=w_file.run, daemon=True)
    th2.start()
    __import__("time").sleep(0.12)
    with events.open("a", encoding="utf-8") as f:
        f.write('{"ts":"2026-10-06T16:00:10.000Z","type":"turn_ended"}\n')
        f.flush()
    deadline = __import__("time").monotonic() + 2.0
    while __import__("time").monotonic() < deadline and not ended2:
        __import__("time").sleep(0.05)
    stop2.set()
    th2.join(timeout=2.0)
    assert ended2 == ["file"]
