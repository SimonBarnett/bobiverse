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


def test_fr6157_stale_markers_cleared_on_restart(tmp_path: Path, monkeypatch):
    """MRB #6164: hang-restart reuses run_dir; stale turn_ended must not reach a new watcher."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    turns = run_dir / "opencode-turns.jsonl"
    turns.write_text(
        json.dumps({"type": "turn_ended", "ts": "2026-11-07T12:00:00Z", "turn_number": 9}) + "\n",
        encoding="utf-8",
    )
    # Mirror Supervisor.start_agent clear (kind=opencode).
    turns.write_text("", encoding="utf-8")
    assert turns.read_text(encoding="utf-8") == ""

    seen = []
    stop = threading.Event()

    def on_ended(turn, wall):
        seen.append(("ended", turn))
        if turn == 1:
            stop.set()

    def on_started(turn, wall):
        seen.append(("started", turn))

    w = bw.GrokTurnWatcher(
        events_path=turns,
        on_turn_started=on_started,
        on_turn_ended=on_ended,
        stop_event=stop,
        poll_s=0.05,
    )
    th = threading.Thread(target=w.run, daemon=True)
    th.start()
    time.sleep(0.08)
    assert ("ended", 9) not in seen
    with turns.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "turn_started", "ts": "2026-11-07T14:00:00Z", "turn_number": 1}) + "\n")
        fh.write(json.dumps({"type": "turn_ended", "ts": "2026-11-07T14:00:01Z", "turn_number": 1}) + "\n")
    stop.wait(2.0)
    th.join(1.0)
    assert ("ended", 9) not in seen
    assert ("started", 1) in seen
    assert ("ended", 1) in seen


def test_fr6157_start_agent_clears_opencode_turns_before_spawn(tmp_path: Path, monkeypatch):
    """Supervisor.start_agent truncates opencode-turns.jsonl before launching a NEW agent."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    turns = run_dir / "opencode-turns.jsonl"
    turns.write_text(
        json.dumps({"type": "turn_ended", "ts": "2026-11-07T12:00:00Z", "turn_number": 3}) + "\n",
        encoding="utf-8",
    )

    class FakeSpec:
        session_id = "oc-new"
        files = {}

    class FakeProc:
        pid = 4242

    launched = {}

    def fake_describe(**kw):
        launched["run_dir"] = kw.get("run_dir")
        return {"spec": FakeSpec(), "env": {}}

    def fake_spawn(spec, env):
        launched["spawned"] = True
        assert turns.read_text(encoding="utf-8") == ""
        return FakeProc()

    monkeypatch.setattr(bw, "describe_agent_child_launch", fake_describe)
    monkeypatch.setattr(bw, "prepare_seat_child_env", lambda base, env: dict(env or {}))
    monkeypatch.setattr(bw, "should_start_cursor_turn_watcher", lambda k: False)
    monkeypatch.setattr(bw, "should_start_turn_watcher", lambda k: False)
    monkeypatch.setattr(bw, "should_start_opencode_turn_watcher", lambda k: False)
    monkeypatch.setattr(bw, "apply_cursor_inject_keys_default", lambda *a, **k: None)
    monkeypatch.setattr(bw, "log_install_root_guard", lambda *a, **k: None)
    monkeypatch.setattr(bw, "parent_of", lambda pid: 0)
    monkeypatch.setattr(bw, "describe_process", lambda pid: (0, "", ""))

    class FakeBored:
        def set_ready(self, v):
            pass

    class FakeRelay:
        def set_target(self, t):
            pass

    class FakeDetector:
        def reset(self, t):
            pass

    import threading as _th

    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup._lock = _th.Lock()
    sup._shutting = False
    sup.bored = FakeBored()
    sup.kind = "opencode"
    sup.run_dir = run_dir
    sup.cwd = str(tmp_path)
    sup.machine = "redqueen"
    sup.nick = "redqueen-1"
    sup.exe = str(tmp_path / "opencode.exe")
    sup.base_env = {}
    sup.secret = None
    sup.proc = None
    sup._owned = set()
    sup.sessions = []
    sup.clock = time.time
    sup.log = lambda *_: None
    sup.detector = FakeDetector()
    sup.relay = FakeRelay()
    sup.startup_grace_s = 0
    sup.spawn = fake_spawn
    sup._prompt = lambda: "hi"
    sup._install_root_for_fuel = lambda: str(tmp_path)
    sup._start_turn_watcher = lambda sid: None
    sup._start_fuel_watcher = lambda pid: None
    sup._start_prompt_watcher = lambda proc: None
    sup._arm_ready = lambda proc: None
    sup._wait_exit = lambda proc: None
    sup._agent_started_at = None
    sup._agent_parent_pid = 0
    sup._agent_parent_image = ""
    sup._agent_parent_cmd = ""
    sup._expected_exit = set()

    ok = bw.Supervisor.start_agent(sup, note="restart")
    assert ok is True
    assert launched.get("spawned") is True
    assert turns.read_text(encoding="utf-8") == ""
