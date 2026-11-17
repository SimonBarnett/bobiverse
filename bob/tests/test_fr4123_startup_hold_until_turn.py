"""FR #4123: startup hold until first turn_ended; cap without turn = hang, not ready."""
from __future__ import annotations

import bob_worker as bw


class FakeProc:
    def __init__(self, pid: int = 4242, *, dead: bool = False):
        self.pid = pid
        self._dead = dead

    def poll(self):
        return 1 if self._dead else None

    def wait(self):
        # FR #7793: exit waiter is stubbed on the Supervisor instance in `_sup`.
        # Returning immediately is fine; do not spin a forever-sleep thread.
        return 1 if self._dead else None


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


def _plant_machine_grok_auth(tmp_path):
    """FR #7183 / #7796: plant the one machine auth store (never seat grok-home)."""
    p = tmp_path / "machine-grok" / "auth.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"issuer::client": {"key": "FAKE_4123"}}', encoding="utf-8")
    return p


def _timer_by_delay(delay: float) -> FakeTimer:
    """FR #7793: pick grace/cap by delay (not instances[0]/[-1] alone)."""
    want = float(delay)
    for t in FakeTimer.instances:
        if abs(float(t.delay) - want) < 0.01:
            return t
    delays = [round(float(x.delay), 3) for x in FakeTimer.instances]
    raise AssertionError(f"no FakeTimer with delay={want}; have {delays}")


def _sup(
    tmp_path,
    monkeypatch,
    *,
    startup_grace_s=60.0,
    startup_min_s=10.0,
    dead=False,
    wait_ready="1",
    ready_cap_s: float | None = None,
):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    monkeypatch.setenv("BOB_WORKER_STARTUP_WAIT_READY", wait_ready)
    monkeypatch.setenv("BOB_WORKER_BORED_ON_TURN_END", "1")
    # FR #7796 / #7793: sign-in reads the machine store, not seat-local grok-home.
    # Isolate from ambient builder env (no ~/.grok/auth.json / foreign GROK_HOME).
    auth = _plant_machine_grok_auth(tmp_path)
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    monkeypatch.delenv("GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_HOME", raising=False)
    if ready_cap_s is not None:
        monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", str(int(ready_cap_s)))
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    restarts: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_fuel_watcher", lambda self, pid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_prompt_watcher", lambda self, proc: None)
    monkeypatch.setattr(
        bw.Supervisor, "_start_grok_signin_guard", lambda self, *a, **k: None
    )

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

    # Seat dir may exist; never plant seat-local grok-home/auth.json (FR #7180).
    (tmp_path / "grok-home").mkdir(parents=True, exist_ok=True)

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
    # FR #7793: suppress the real exit-waiter thread so a dead FakeProc cannot
    # race the cap callback with agent-cli-nonzero-exit (FR #7177 ordering).
    sup._wait_exit = lambda *a, **k: None  # type: ignore[method-assign]
    return sup, logs, clock, injected, relay, bored, restarts


def test_fr4123_slow_first_turn_no_bored_or_inject_before_turn_ended(tmp_path, monkeypatch):
    """Spawn t=0; turn_started 266s; turn_ended 700s -> no ready/inject before 700s."""
    sup, logs, clock, injected, relay, bored, restarts = _sup(
        tmp_path, monkeypatch, ready_cap_s=900
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    # grace at 60s: still hold
    clock["t"] = 60.0
    _timer_by_delay(60.0).fn()
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
    # FR #7796: the held assignment is flushed exactly once when the hold releases.
    assert len(injected) == 1
    assert "MRB o/r#1 https://x/1" in injected[0]


def test_fr4123_turn_started_still_held_at_grace_until_turn_ended(tmp_path, monkeypatch):
    sup, logs, clock, injected, relay, bored, restarts = _sup(
        tmp_path, monkeypatch, ready_cap_s=900
    )
    assert sup.start_agent()
    sid = sup.sessions[-1]
    clock["t"] = 5.0
    sup._note_startup_turn_started(sid)
    clock["t"] = 60.0
    _timer_by_delay(60.0).fn()
    assert bored.ready is False
    assert "ready" not in bored.fires
    clock["t"] = 90.0
    sup._maybe_ready_on_first_turn_ended(sid)
    assert bored.ready is True
    assert restarts == []


def test_fr4123_cap_without_turn_hangs_when_process_dead(tmp_path, monkeypatch):
    """No events; process dead at cap -> hang path, never ready/inject.

    FR #7793: assert the cap reason exactly. Do not require it to be restarts[0]
    when an exit-waiter race could prepend agent-cli-nonzero-exit (FR #7177).
    """
    # Hostile ambient: foreign GROK_AUTH_PATH must not win over planted machine auth.
    monkeypatch.setenv("GROK_AUTH_PATH", str(tmp_path / "absent-ambient-auth.json"))
    monkeypatch.setenv("BOB_WORKER_STARTUP_WAIT_READY", "0")  # overridden inside _sup
    sup, logs, clock, injected, relay, bored, restarts = _sup(
        tmp_path, monkeypatch, dead=True, ready_cap_s=600
    )
    assert sup.start_agent()
    # kill the live handle the same way poll would report
    with sup._lock:
        if sup.proc is not None:
            sup.proc._dead = True
    _timer_by_delay(60.0).fn()  # grace -> arm cap (540s remaining of 600)
    _timer_by_delay(540.0).fn()  # cap
    assert restarts == ["startup-no-first-turn"], restarts
    assert getattr(sup, "_startup_hold_armed", True) is False
    assert bored.ready is False
    assert injected == []
    assert not any("startup ready cap" in m and "inject + !bored enabled" in m for m in logs)


def test_fr4123_cap_without_turn_hangs_when_process_idle(tmp_path, monkeypatch):
    """No events; alive (idle or busy) at hard cap without turn_ended -> hang, not ready."""
    monkeypatch.setenv("GROK_AUTH_PATH", str(tmp_path / "absent-ambient-auth.json"))
    sup, logs, clock, injected, relay, bored, restarts = _sup(
        tmp_path, monkeypatch, ready_cap_s=600
    )
    assert sup.start_agent()
    monkeypatch.setattr(bw, "_startup_proc_idle", lambda proc, probe=None: True)
    _timer_by_delay(60.0).fn()
    _timer_by_delay(540.0).fn()
    assert restarts == ["startup-no-first-turn"], restarts
    assert getattr(sup, "_startup_hold_armed", True) is False
    assert bored.ready is False
    assert injected == []
    assert any("hang-recycle" in m for m in logs)


def test_fr4123_legacy_grace_defers_bored_while_turn_open(tmp_path, monkeypatch):
    """wait_ready=0 + signed-in (FR #7180): ready immediately, no first-turn wait."""
    monkeypatch.setenv("GROK_AUTH_PATH", str(tmp_path / "absent-ambient-auth.json"))
    sup, logs, clock, injected, relay, bored, restarts = _sup(
        tmp_path, monkeypatch, wait_ready="0"
    )
    assert sup.start_agent()
    assert bored.ready is True
    assert "ready" in bored.fires
    assert any("signed in" in m for m in logs)
