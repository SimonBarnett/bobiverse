"""FR #4123: startup hold until first turn_ended; cap without turn = hang, not ready."""
from __future__ import annotations

import time

import bob_worker as bw


class FakeProc:
    def __init__(self, pid: int = 4242, *, dead: bool = False):
        self.pid = pid
        self._dead = dead

    def poll(self):
        return 1 if self._dead else None

    def wait(self):
        while self.poll() is None:
            time.sleep(0.05)
        return self.poll()


class FakeTimer:
    instances: list = []

    def __init__(self, delay, fn):
        self.delay = float(delay)
        self.fn = fn
        self.daemon = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


def _sup(tmp_path, monkeypatch, *, startup_grace_s=60.0, startup_min_s=10.0, dead=False):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    monkeypatch.delenv("BOB_WORKER_STARTUP_WAIT_READY", raising=False)
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    restarts: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_fuel_watcher", lambda self, pid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_prompt_watcher", lambda self, proc: None)

    class FakeBored:
        def __init__(self):
            self.ready = False
            self.fires: list[str] = []

        def set_ready(self, ready: bool):
            self.ready = bool(ready)
            if ready:
                self.fires.append("ready")

        def activity(self, mark_work=True):
            pass

        def nak(self):
            pass

        def turn_started(self, *a, **k):
            pass

        def turn_ended(self, *a, **k):
            pass

        def clear_held_assign(self):
            pass

        @property
        def holding_incoming_assigns(self):
            return False

        def note_held_assign(self):
            pass

        def stop(self):
            pass

        @property
        def ack_open(self):
            return False

    bored = FakeBored()

    def spawn(spec, env):
        return FakeProc(pid=9001, dead=dead)

    def inject(pid, line):
        injected.append(line)
        return True

    def restart(self, reason: str):
        restarts.append(reason)
        logs.append(f"agent: HUNG ({reason}); restart")
        with self._lock:
            self._startup_hold_armed = False
            self.proc = None
        self.relay.set_target(None)
        self.bored.set_ready(False)

    monkeypatch.setattr(bw.Supervisor, "restart_agent", restart)

    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-42052",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=spawn,
        inject=inject,
        startup_grace_s=startup_grace_s,
        startup_min_s=startup_min_s,
        clock=lambda: clock["t"],
        bored=bored,
    )
    return sup, logs, clock, injected, relay, bored, restarts


def test_fr4123_slow_first_turn_no_bored_or_inject_before_turn_ended(tmp_path, monkeypatch):
    """Spawn t=0; turn_started 266s; turn_ended 700s -> no ready/inject before 700s."""
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "900")
    sup, logs, clock, injected, relay, bored, restarts = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    sid = sup.sessions[-1]
    # grace at 60s: still hold
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()
    assert bored.ready is False
    assert "ready" not in bored.fires
    assert any("session not ready" in m for m in logs)
    # turn_started at 266s: still hold
    clock["t"] = 266.0
    sup._note_startup_turn_started(sid)
    assert bored.ready is False
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-42052: MRB o/r#1 https://x/1") == "held"
    assert injected == []
    # turn_ended at 700s: release
    clock["t"] = 700.0
    sup._maybe_ready_on_first_turn_ended(sid)
    assert bored.ready is True
    assert any("first turn_ended" in m for m in logs)
    assert restarts == []


def test_fr4123_turn_started_still_held_at_grace_until_turn_ended(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "900")
    sup, logs, clock, injected, relay, bored, restarts = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 5.0
    sup._note_startup_turn_started(sid)
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()
    assert bored.ready is False
    assert "ready" not in bored.fires
    clock["t"] = 90.0
    sup._maybe_ready_on_first_turn_ended(sid)
    assert bored.ready is True
    assert restarts == []


def test_fr4123_cap_without_turn_hangs_when_process_dead(tmp_path, monkeypatch):
    """No events; process dead at cap -> hang path, never ready/inject."""
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "600")
    sup, logs, clock, injected, relay, bored, restarts = _sup(tmp_path, monkeypatch, dead=True)
    assert sup.start_agent()
    # kill the live handle the same way poll would report
    with sup._lock:
        if sup.proc is not None:
            sup.proc._dead = True
    FakeTimer.instances[0].fn()  # grace -> arm cap
    FakeTimer.instances[-1].fn()  # cap
    assert restarts and "startup" in restarts[0]
    assert bored.ready is False
    assert not any("startup ready cap" in m and "inject + !bored enabled" in m for m in logs)


def test_fr4123_cap_without_turn_hangs_when_process_idle(tmp_path, monkeypatch):
    """No events; alive (idle or busy) at hard cap without turn_ended -> hang, not ready."""
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "600")
    sup, logs, clock, injected, relay, bored, restarts = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    monkeypatch.setattr(bw, "_startup_proc_idle", lambda proc, probe=None: True)
    FakeTimer.instances[0].fn()
    FakeTimer.instances[-1].fn()
    assert restarts and "startup" in restarts[0]
    assert bored.ready is False
    assert any("hang-recycle" in m for m in logs)


def test_fr4123_legacy_grace_defers_bored_while_turn_open(tmp_path, monkeypatch):
    """wait_ready=0 grace release mid-turn: inject ok, !bored deferred until turn_ended."""
    monkeypatch.setenv("BOB_WORKER_STARTUP_WAIT_READY", "0")
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_fuel_watcher", lambda self, pid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_prompt_watcher", lambda self, proc: None)

    class FakeBored:
        def __init__(self):
            self.ready = False
            self.fires = []

        def set_ready(self, ready: bool):
            self.ready = bool(ready)
            if ready:
                self.fires.append("ready")

        def activity(self, mark_work=True):
            pass

        def nak(self):
            pass

        def turn_started(self, *a, **k):
            pass

        def turn_ended(self, *a, **k):
            pass

        def clear_held_assign(self):
            pass

        @property
        def holding_incoming_assigns(self):
            return False

        def note_held_assign(self):
            pass

        def stop(self):
            pass

    bored = FakeBored()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=lambda s, e: FakeProc(),
        inject=lambda p, l: injected.append(l) or True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 5.0
    sup._note_startup_turn_started(sid)
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()
    # inject path armed but !bored deferred while turn 0 open
    assert "ready" not in bored.fires
    assert any("deferring !bored" in m for m in logs)
    assert getattr(sup, "_startup_defer_start_bored", False) is True
    clock["t"] = 90.0
    sup._release_deferred_startup_bored()
    assert bored.ready is True
    assert "ready" in bored.fires
