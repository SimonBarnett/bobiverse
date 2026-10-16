"""MRB #4462: Cursor turn watcher defaults inject to batched KEY_EVENT."""
from __future__ import annotations

import os
from pathlib import Path

import bob_worker as bw


class _Thread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        return None


class _Seat:
    def __init__(self):
        self.logs = []
        self.bored = object()
        self._turn_watch_stop = None
        self._turn_watch_thread = None

    def log(self, msg):
        self.logs.append(msg)


def test_mrb4462_cursor_watcher_sets_inject_paste_zero(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    monkeypatch.setattr(bw.threading, "Thread", _Thread)
    seat = _Seat()
    bw.Supervisor._start_cursor_turn_watcher(seat)
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("batched keys" in line for line in seat.logs)


def test_mrb4462_explicit_inject_paste_wins(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    monkeypatch.setattr(bw.threading, "Thread", _Thread)
    seat = _Seat()
    bw.Supervisor._start_cursor_turn_watcher(seat)
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "1"
    assert not any("batched keys" in line for line in seat.logs)


def test_mrb4462_skill_documents_cursor_keys_default():
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    needle = "_start_cursor_turn_watcher` sets `BOB_WORKER_INJECT_PASTE=0`"
    assert needle in text
    assert "literal v" in text
