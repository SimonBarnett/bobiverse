"""FR #2884: first grok turn_ended after spawn ends startup hold; startup_grace_s is fallback."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw


class FakeProc:
    def __init__(self, pid: int = 4242):
        self.pid = pid

    def poll(self):
        return None

    def wait(self):
        while True:
            time.sleep(0.05)


class FakeTimer:
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


FakeTimer.instances: list = []

def _wait_bored(irc, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(txt == "!bored" for _t, txt in irc.said):
            return True
        time.sleep(0.02)
    return False




def _sup(tmp_path, monkeypatch, *, kind="grok", startup_grace_s=60.0, startup_min_s=10.0, irc=None, bored=None):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)

    def spawn(spec, env):
        return FakeProc(pid=9000 + len(logs))

    def inject(pid, line):
        injected.append(line)
        return True

    # Avoid real watcher thread; tests drive _maybe_ready_on_first_turn_ended.
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)

    kw = dict(
        kind=kind,
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-42052",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        spawn=spawn,
        inject=inject,
        startup_grace_s=startup_grace_s,
        startup_min_s=startup_min_s,
        clock=lambda: clock["t"],
    )
    if bored is not None:
        kw["bored"] = bored
    elif irc is None:
        # Minimal bored that records set_ready; reason=start needs irc for real BoredEmitter.
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

        kw["bored"] = FakeBored()

    sup = bw.Supervisor(**kw)
    return sup, logs, clock, injected, relay


class _Irc:
    def __init__(self):
        self.alive = True
        self.shop = "#marchhare"
        self.said: list = []
        self.on_nak = None
        self.on_lost = None
        self.on_message = None

    def say(self, target, text):
        self.said.append((target, text))
        return True

    def close(self, why=""):
        self.alive = False


def test_first_turn_ended_releases_startup_hold_and_fires_start(tmp_path, monkeypatch):
    irc = _Irc()
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)

    def spawn(spec, env):
        return FakeProc()

    bored = bw.BoredEmitter(
        lambda: irc.say(irc.shop, "!bored") or True,
        logs.append,
        clock=lambda: clock["t"],
        idle_s=120.0,
        repeat_s=180.0,
        harvest_hold_s=90.0,
    )
    bored.start()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-42052",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        spawn=spawn,
        inject=lambda p, l: injected.append(l) or True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    assert FakeTimer.instances and FakeTimer.instances[0].delay == 60.0
    assert ("#marchhare", "!bored") not in irc.said

    clock["t"] = 2.0
    sup._note_startup_turn_started(sid)
    clock["t"] = 24.0
    sup._maybe_ready_on_first_turn_ended(sid)

    assert any("first turn_ended" in m for m in logs), logs
    assert any("fallback not needed" in m for m in logs)
    assert _wait_bored(irc), irc.said
    assert sum(1 for t, txt in irc.said if txt == "!bored") == 1
    assert FakeTimer.instances[0].cancelled is True
    # Assign inject now works
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-42052: MRB o/r#1 https://x/1") in (
        "injected",
        "held",
        "coalescing",
    )
    bored.stop()


def test_grace_fallback_when_no_turn_ended(tmp_path, monkeypatch):
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    assert FakeTimer.instances[0].delay == 60.0
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()
    assert any("startup_grace_s=60 fallback" in m or "startup_grace_s=60" in m for m in logs)
    assert "ready" in getattr(sup.bored, "fires", [])


def test_grace_timer_after_turn_release_is_noop(tmp_path, monkeypatch):
    irc = _Irc()
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    fires: list[str] = []

    bored = bw.BoredEmitter(
        lambda: (fires.append("bored") or irc.say(irc.shop, "!bored") or True),
        logs.append,
        clock=lambda: clock["t"],
    )
    bored.start()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        spawn=lambda s, e: FakeProc(),
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 24.0
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended(sid)
    assert _wait_bored(irc), irc.said
    n = sum(1 for _t, txt in irc.said if txt == "!bored")
    FakeTimer.instances[0].fn()  # late grace
    time.sleep(0.1)
    assert sum(1 for _t, txt in irc.said if txt == "!bored") == n == 1
    bored.stop()


def test_turn_ended_from_other_session_ignored(tmp_path, monkeypatch):
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 24.0
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended("other-session-id")
    assert not any("agent: ready" in m for m in logs)
    assert getattr(sup.bored, "ready", False) is False


def test_startup_min_floor(tmp_path, monkeypatch):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    class FakeBored:
        def __init__(self):
            self.ready = False
        def set_ready(self, ready: bool):
            self.ready = bool(ready)
        def activity(self, mark_work=True):
            pass
        def nak(self):
            pass
        @property
        def holding_incoming_assigns(self):
            return False
        def note_held_assign(self):
            pass
        def clear_held_assign(self):
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
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 3.0
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended(sid)
    assert bored.ready is False
    # Min-floor timer scheduled for remaining 7s
    min_timers = [t for t in FakeTimer.instances if abs(t.delay - 7.0) < 0.01]
    assert min_timers, [t.delay for t in FakeTimer.instances]
    clock["t"] = 10.0
    min_timers[0].fn()
    assert bored.ready is True
    assert any("first turn_ended" in m for m in logs)


def test_no_inject_before_release(tmp_path, monkeypatch):
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    clock["t"] = 5.0
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-42052: MRB o/r#9 https://x/9") == "held"
    assert injected == []
    sid = sup.sessions[-1]
    clock["t"] = 24.0
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended(sid)
    assert any("MRB" in x or "FROM" in x for x in injected) or relay.injected >= 1


def test_stale_build_check_runs_at_turn_release(tmp_path, monkeypatch):
    irc = _Irc()
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    bored = bw.BoredEmitter(
        lambda: True,  # post_bored wired below after Supervisor exists
        logs.append,
        clock=lambda: clock["t"],
    )
    # Build supervisor first then wire post_bored to real method
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        spawn=lambda s, e: FakeProc(),
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    bored.send = sup.post_bored
    bored.start()
    sup.stale_build_check = lambda: "run=old install=new"
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 24.0
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended(sid)
    deadline = time.time() + 2.0
    while time.time() < deadline and not any("stale build" in m for m in logs):
        time.sleep(0.02)
    assert ("#marchhare", "!bored") not in irc.said
    assert any("stale build" in m for m in logs)
    assert FakeTimer.instances[0].cancelled is True
    bored.stop()


def test_restart_rearms_hold(tmp_path, monkeypatch):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    procs: list = []

    def spawn(spec, env):
        p = FakeProc(pid=1000 + len(procs))
        procs.append(p)
        return p

    class FakeBored:
        def __init__(self):
            self.ready = False
            self.n = 0

        def set_ready(self, ready: bool):
            self.ready = bool(ready)
            if ready:
                self.n += 1

        def activity(self, mark_work=True):
            pass

        def nak(self):
            pass

        @property
        def holding_incoming_assigns(self):
            return False

        def note_held_assign(self):
            pass

        def clear_held_assign(self):
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
        spawn=spawn,
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid1 = sup.sessions[-1]
    proc1 = sup.proc
    clock["t"] = 24.0
    sup._note_startup_turn_started(sid1)
    # Simulate restart: mark old proc gone and start new agent
    clock["t"] = 30.0
    with sup._lock:
        sup.proc = None
    bored.ready = False
    assert sup.start_agent()
    sid2 = sup.sessions[-1]
    assert sid2 != sid1
    # Old session turn_ended must not release new hold
    clock["t"] = 40.0
    sup._maybe_ready_on_first_turn_ended(sid1)
    assert bored.ready is False
    sup._note_startup_turn_started(sid2)
    sup._maybe_ready_on_first_turn_ended(sid2)
    assert bored.ready is True
    assert bored.n == 1
    # Stale ready for old proc is noop
    sup._ready_now(proc1, reason="turn")
    assert bored.n == 1


def test_non_grok_kind_keeps_timer(tmp_path, monkeypatch):
    # cursor kind: no turn watcher path used; only grace timer
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    # Real _start_turn_watcher should no-op for non-grok
    class FakeBored:
        def __init__(self):
            self.ready = False
        def set_ready(self, ready: bool):
            self.ready = bool(ready)
        def activity(self, mark_work=True):
            pass
        def nak(self):
            pass
        @property
        def holding_incoming_assigns(self):
            return False
        def note_held_assign(self):
            pass
        def clear_held_assign(self):
            pass

    bored = FakeBored()
    sup = bw.Supervisor(
        kind="cursor",
        exe=r"C:\x\agent.cmd",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=tmp_path,
        irc=None,
        relay=relay,
        log=logs.append,
        spawn=lambda s, e: FakeProc(),
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    assert FakeTimer.instances and FakeTimer.instances[0].delay == 60.0
    clock["t"] = 24.0
    # Even if someone calls turn_ended helper, non-armed watcher session may still be set —
    # FR: non-grok keeps timer. Our hold still allows turn path if session set; for cursor
    # start_agent still arms startup hold. Spec says non-grok kinds keep plain 60s timer
    # because no turn watcher. Calling maybe_ready should be ignored when kind has no watcher
    # OR when we never get turn events. Test: only grace releases.
    assert bored.ready is False
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()
    assert bored.ready is True


def test_replay_42052_timeline(tmp_path, monkeypatch):
    """spawn 18:37:43, turn_ended 18:38:04 → reason=start at +21s, not +60s."""
    irc = _Irc()
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    logs: list[str] = []
    clock = {"t": 0.0}
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    bored = bw.BoredEmitter(
        lambda: irc.say(irc.shop, "!bored") or True,
        logs.append,
        clock=lambda: clock["t"],
    )
    bored.start()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-42052",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        spawn=lambda s, e: FakeProc(),
        inject=lambda p, l: True,
        startup_grace_s=60.0,
        startup_min_s=10.0,
        clock=lambda: clock["t"],
        bored=bored,
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 21.0  # 18:38:04 - 18:37:43
    sup._note_startup_turn_started(sid)
    sup._maybe_ready_on_first_turn_ended(sid)
    assert clock["t"] == 21.0
    assert _wait_bored(irc), irc.said
    assert clock["t"] < 60.0
    bored.stop()
