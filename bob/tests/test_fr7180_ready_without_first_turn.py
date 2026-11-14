"""FR #7180: signed-in seats !bored without a first turn; unsigned never ready."""
from __future__ import annotations

import json
import time
from pathlib import Path

import bob_worker as bw


class FakeProc:
    def __init__(self, pid: int = 7180):
        self.pid = pid

    def poll(self):
        return None

    def wait(self):
        while True:
            time.sleep(0.05)


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


def _plant_grok_auth(tmp_path: Path) -> None:
    p = tmp_path / "grok-home" / "auth.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"issuer::client": {"key": "FAKE_7180"}}), encoding="utf-8")


def _sup(tmp_path, monkeypatch, *, plant_auth: bool):
    FakeTimer.instances.clear()
    monkeypatch.setattr(bw.threading, "Timer", FakeTimer)
    monkeypatch.delenv("BOB_WORKER_STARTUP_WAIT_READY", raising=False)
    logs: list[str] = []
    clock = {"t": 0.0}
    injected: list[str] = []
    relay = bw.Relay(logs.append, clock=lambda: clock["t"], persist_dir=tmp_path)
    monkeypatch.setattr(bw.Supervisor, "_start_turn_watcher", lambda self, sid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_fuel_watcher", lambda self, pid: None)
    monkeypatch.setattr(bw.Supervisor, "_start_prompt_watcher", lambda self, proc: None)
    if plant_auth:
        _plant_grok_auth(tmp_path)
    bored = FakeBored()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="flamingo",
        nick="flamingo-7180",
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
    return sup, logs, clock, injected, relay, bored


def test_fr7180_signed_in_ready_without_first_turn(tmp_path, monkeypatch):
    """Fake agent never ends a turn: still ready + !bored when auth.json is present."""
    sup, logs, clock, injected, relay, bored = _sup(tmp_path, monkeypatch, plant_auth=True)
    assert sup.start_agent()
    assert bored.ready is True
    assert "ready" in bored.fires
    assert getattr(sup, "_session_assignable", False) is True
    assert any("signed in" in m and "first turn" in m for m in logs)
    assert relay.deliver(
        "Jeeves", "#flamingo", "flamingo-7180: FR SimonBarnett/bobiverse#7180 https://x/1"
    ) in ("injected", "held", "coalescing")


def test_fr7180_unsigned_never_ready(tmp_path, monkeypatch):
    empty = tmp_path / "empty-user-grok"
    empty.mkdir()
    import skill_dag_bound as sdb

    monkeypatch.setattr(sdb, "default_user_grok_home", lambda: empty)
    sup, logs, clock, injected, relay, bored = _sup(tmp_path, monkeypatch, plant_auth=False)
    assert sup.start_agent()
    assert bored.ready is False
    assert "ready" not in bored.fires
    assert getattr(sup, "_session_assignable", True) is False
    assert any("needs sign-in" in m for m in logs)
    assert relay.deliver(
        "Jeeves", "#flamingo", "flamingo-7180: FR SimonBarnett/bobiverse#7180 https://x/1"
    ) == "held"


def test_fr7180_hello_lines():
    assert bw.worker_needs_signin_line("grok") == "worker needs sign-in kind=grok"
    line = bw.worker_hello_line("grok", model="grok-4.5", build="abc123def456")
    assert line.startswith("worker ready ")
    assert "kind=grok" in line


def test_fr7180_digest_assignable_false(monkeypatch):
    payload_holder = {}

    def fake_post(url, payload, log=None):
        payload_holder.update(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", fake_post)
    ok = bw.post_digest_seat_kind(
        machine="flamingo",
        pid=7180,
        nick="flamingo-7180",
        kind="grok",
        assignable=False,
    )
    assert ok is True
    assert payload_holder.get("assignable") is False
    assert payload_holder.get("error") == "needs-sign-in"
    assert payload_holder.get("state") == "needs-sign-in"


def test_fr7180_system_profile_auth_ignored(tmp_path):
    """Seat uses run_dir/grok-home, not SYSTEM ~/.grok (FR #7180)."""
    assert bw.agent_grok_home(run_dir=tmp_path) == tmp_path / "grok-home"
    assert bw.grok_agent_signed_in(run_dir=tmp_path) is False
    _plant_grok_auth(tmp_path)
    assert bw.grok_agent_signed_in(run_dir=tmp_path) is True


def test_fr7180_docs_and_wait_ready_default(monkeypatch):
    from repo_layout import ROOT

    monkeypatch.delenv("BOB_WORKER_STARTUP_WAIT_READY", raising=False)
    assert bw._startup_wait_ready_enabled() is False
    docs = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "FR #7180" in docs
    assert "needs sign-in" in docs.lower() or "needs-sign-in" in docs
