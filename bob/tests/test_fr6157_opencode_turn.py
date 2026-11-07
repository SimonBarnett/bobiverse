"""FR #6157: OpenCode turn_ended into BoredEmitter; startup/done-miss pins."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import bob_worker as bw


def test_fr6157_should_start_opencode_turn_watcher(monkeypatch):
    assert bw.should_start_opencode_turn_watcher("opencode") is True
    assert bw.should_start_opencode_turn_watcher("grok") is False
    assert bw.should_start_opencode_turn_watcher("cursor") is False
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "0")
    assert bw.should_start_opencode_turn_watcher("opencode") is False
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "1")
    monkeypatch.setenv("BOB_WORKER_OPENCODE_TURN_WATCH", "0")
    assert bw.should_start_opencode_turn_watcher("opencode") is False


def test_fr6157_launch_wrapper_writes_turn_markers(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        str(tmp_path / "opencode.exe"),
        tmp_path / "run",
        None,
    )
    script_key = next(k for k in spec.files if str(k).endswith("launch-opencode.ps1"))
    ps1 = spec.files[script_key]
    assert "opencode-turns.jsonl" in ps1
    assert "turn_started" in ps1
    assert "turn_ended" in ps1
    assert "FR #6157" in ps1 or "6157" in ps1


def test_fr6157_opencode_turn_watcher_emits_ended(tmp_path: Path):
    log = tmp_path / "opencode-turns.jsonl"
    seen = []
    stop = threading.Event()

    def on_ended(turn, wall):
        seen.append(("ended", turn))
        stop.set()

    def on_started(turn, wall):
        seen.append(("started", turn))

    w = bw.GrokTurnWatcher(
        events_path=log,
        on_turn_started=on_started,
        on_turn_ended=on_ended,
        stop_event=stop,
        poll_s=0.05,
    )
    th = threading.Thread(target=w.run, daemon=True)
    th.start()
    time.sleep(0.08)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "turn_started", "ts": "2026-11-07T14:00:00Z", "turn_number": 1}) + "\n")
        fh.write(json.dumps({"type": "turn_ended", "ts": "2026-11-07T14:00:01Z", "turn_number": 1}) + "\n")
    stop.wait(2.0)
    th.join(1.0)
    assert ("started", 1) in seen
    assert ("ended", 1) in seen


def test_fr6157_bored_done_miss_arms_on_opencode_turn_ended():
    """turn_ended with ACK open and no DONE arms done-miss (same BoredEmitter path)."""
    events = []
    bored = bw.BoredEmitter(
        send=lambda: events.append("bored") or True,
        log=lambda *_: None,
        idle_s=9999,
        repeat_s=9999,
        harvest_hold_s=90.0,
        done_miss_grace_s=5.0,
    )
    bored.set_ready(True)
    bored.on_outbox("ACK FR owner/repo#1")
    bored.turn_started(turn=1, sid="oc")
    bored.turn_ended(turn=1, sid="oc")
    assert bored._done_miss_armed_at is not None
    assert bored._ack_open is True


def test_fr6157_startup_arm_enables_opencode_turn_release(monkeypatch):
    """OpenCode seats use turn release (not Grok events.jsonl); wait_ready must not hang on grok."""
    assert bw.should_start_opencode_turn_watcher("opencode") is True
    # _arm_ready sets _startup_turn_release_enabled from grok OR opencode watchers
    # Pin the helper used by Supervisor._arm_ready after FR #6157.
    assert hasattr(bw, "startup_turn_release_enabled")
    assert bw.startup_turn_release_enabled("opencode") is True
    assert bw.startup_turn_release_enabled("grok") is True
    assert bw.startup_turn_release_enabled("cursor") is False


def test_fr6157_start_turn_watcher_routes_opencode(monkeypatch, tmp_path: Path):
    """Supervisor._start_turn_watcher starts jsonl watcher for opencode, not grok session dir."""
    started = {}

    class FakeWatcher:
        def __init__(self, **kw):
            started["kw"] = kw
            self.poll_s = 0.5

        def run(self):
            return None

    monkeypatch.setattr(bw, "GrokTurnWatcher", FakeWatcher)
    monkeypatch.setattr(bw, "should_start_cursor_turn_watcher", lambda k: False)
    monkeypatch.setattr(bw, "should_start_turn_watcher", lambda k: False)
    monkeypatch.setattr(bw, "should_start_opencode_turn_watcher", lambda k: True)

    class FakeBored:
        def turn_started(self, **k):
            pass

        def turn_ended(self, **k):
            pass

        def clear_held_assign(self):
            pass

    class FakeRelay:
        def release_held_assigns(self):
            return 0

    class FakeIrc:
        alive = False
        shop = "#x"

    # Minimal Supervisor-like object using real method
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.bored = FakeBored()
    sup.relay = FakeRelay()
    sup.irc = FakeIrc()
    sup.log = lambda *_: None
    sup.cwd = str(tmp_path)
    sup.run_dir = tmp_path / "run"
    sup.run_dir.mkdir()
    sup.sessions = ["oc-1"]
    sup._turn_watch_stop = None
    sup._turn_watch_thread = None
    sup._cursor_turn_watcher = None
    sup._stop_turn_watcher = lambda: None
    # bind real method
    sup._start_turn_watcher = bw.Supervisor._start_turn_watcher.__get__(sup, bw.Supervisor)
    # stub _maybe_ready / note
    sup._note_startup_turn_started = lambda sid: None
    sup._maybe_ready_on_first_turn_ended = lambda sid: None
    sup._prompt_watch = None

    bw.Supervisor._start_turn_watcher(sup, "oc-1")
    assert "kw" in started
    path_fn = started["kw"].get("events_path_fn")
    assert callable(path_fn)
    p = path_fn()
    assert p is not None
    assert str(p).endswith("opencode-turns.jsonl")
    assert "events.jsonl" not in str(p)