"""FR #4464: Cursor KEY_EVENT default is applied at seat start, not only in the turn watcher."""
from __future__ import annotations

import os

import bob_worker as bw


class _Proc:
    def __init__(self, pid: int = 4242):
        self.pid = pid

    def poll(self):
        return None


class _Thread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        return None


def test_fr4464_helper_sets_keys_for_cursor_when_unset(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    logs: list[str] = []
    assert bw.apply_cursor_inject_keys_default("cursor", log=logs.append) is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("batched keys" in line for line in logs)


def test_fr4464_helper_skips_non_cursor_and_explicit(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    assert bw.apply_cursor_inject_keys_default("grok") is False
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") in (None, "")
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    assert bw.apply_cursor_inject_keys_default("cursor") is False
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "1"


def test_fr4464_start_agent_sets_keys_when_turn_watch_off(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    monkeypatch.setenv("BOB_WORKER_CURSOR_TURN_WATCH", "0")
    monkeypatch.setattr(bw.threading, "Thread", _Thread)
    logs: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: 0.0, persist_dir=tmp_path)

    def spawn(spec, env):
        return _Proc()

    sup = bw.Supervisor(
        kind="cursor",
        exe=r"C:\x\agent.cmd",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-21652",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=spawn,
        startup_grace_s=0,
        clock=lambda: 0.0,
    )
    assert bw.should_start_cursor_turn_watcher("cursor") is False
    assert sup.start_agent() is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("batched keys" in line for line in logs)
