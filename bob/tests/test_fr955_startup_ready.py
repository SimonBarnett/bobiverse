"""FR #955: hold inject/!bored until startup grace; IRC connect retries; early-exit log."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw


def test_default_startup_grace_is_at_least_60():
    # Constructor default (tests may override to 0).
    import inspect

    sig = inspect.signature(bw.Supervisor.__init__)
    default = sig.parameters["startup_grace_s"].default
    assert float(default) >= 60.0


def test_grace_holds_inject_until_timer(tmp_path, monkeypatch):
    logs: list[str] = []
    clock = {"t": 0.0}

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

        def wait(self):
            while True:
                time.sleep(0.05)

    injected: list[str] = []

    def spawn(spec, env):
        return FakeProc()

    def inject(pid, line):
        injected.append(line)
        return True

    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    bored_fires: list[str] = []

    class FakeBored:
        def set_ready(self, ready: bool):
            if ready:
                bored_fires.append("ready")

        def activity(self):
            pass

        def nak(self):
            pass

    timers: list = []

    class FakeTimer:
        def __init__(self, delay, fn):
            self.delay = delay
            self.fn = fn
            self.daemon = False
            timers.append(self)

        def start(self):
            pass

    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)

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
        inject=inject,
        startup_grace_s=60.0,
        clock=lambda: clock["t"],
        bored=FakeBored(),
    )
    assert sup.start_agent()
    # During grace: deliver holds (no inject target).
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-1: MRB o/r#1 https://x/1") == "held"
    assert injected == []
    assert bored_fires == []
    assert timers and timers[0].delay == 60.0
    # Fire grace callback.
    timers[0].fn()
    assert "ready" in bored_fires
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-1: ping") in ("injected", "held", "coalescing")
    # Pending flush on set_target should have injected the held assign.
    assert any("MRB" in x or "FROM" in x for x in injected) or relay.injected >= 1


def test_connect_with_retries_succeeds_on_second_attempt(monkeypatch):
    logs: list[str] = []
    calls = {"n": 0}

    seat = bw.IrcSeat(
        "127.0.0.1",
        1,
        "marchhare-1",
        "marchhare",
        tls=False,
        log=logs.append,
        connect=lambda: (_ for _ in ()).throw(ConnectionError("boom")),
    )

    def flaky_connect(timeout=45.0):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("IRC registration timed out")
        # Mark registered without a real socket for the success path.
        seat.registered.set()
        seat.sock = object()  # type: ignore

    monkeypatch.setattr(seat, "connect", flaky_connect)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    seat.connect_with_retries(attempts=3, timeout=1.0, backoff_s=(0.01, 0.01, 0.01))
    assert calls["n"] == 2
    assert any("attempt 1/3 failed" in m for m in logs)


def test_early_exit_logs_last_injected(tmp_path, monkeypatch):
    logs: list[str] = []
    clock = {"t": 0.0}

    class FakeProc:
        pid = 99

        def poll(self):
            return 0

        def wait(self):
            return 0

    relay = bw.Relay(logs.append, clock=lambda: clock["t"])
    relay.last_unacked = "FROM Jeeves #m marchhare-1: MRB SimonBarnett/bobiverse#660 https://x"

    def spawn(spec, env):
        return FakeProc()

    class FakeTimer:
        def __init__(self, *a, **k):
            self.daemon = False

        def start(self):
            return None

        def cancel(self):
            return None

    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)

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
        clock=lambda: clock["t"],
        bored=None,
    )
    assert sup.start_agent()
    clock["t"] = 5.0  # early
    sup._wait_exit(sup.proc)
    assert any("early exit" in m and "last_injected=" in m for m in logs)


def test_connect_with_retries_has_no_dead_code_after_raise():
    """MRB #956 hostile: unreachable JOIN/failed after raise last must not remain."""
    import inspect
    src = inspect.getsource(bw.IrcSeat.connect_with_retries)
    assert "raise last" in src
    # Nothing after the final raise in the function body.
    tail = src.split("raise last", 1)[1]
    assert "JOIN" not in tail
    assert "self.failed" not in tail
