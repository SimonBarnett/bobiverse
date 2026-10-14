"""FR #4180: out-of-fuel hold must stop ack-miss / HUNG respawns and refuse new assigns.

While the seat is in the out-of-fuel hold (402 / exhausted reading), the ack-miss and
HangDetector paths must not recycle or respawn the agent, must not re-inject assigns,
must NACK arriving assigns with out-of-fuel, and must stay quiet (!bored suppressed)
until fuel returns. Restart counting is monotonic per incident so 3/3 is reachable.
Unknown/failed fuel readings still do not count as exhausted (FR #3923).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_assign_job_type_key_parses_fr_mrb_uat():
    line = (
        "FROM Jeeves #marchhare marchhare-1: FR SimonBarnett/a-search#1176 "
        "https://github.com/SimonBarnett/a-search/issues/1176"
    )
    assert bw.assign_job_type_key(line) == "FR SimonBarnett/a-search#1176"
    assert bw.assign_job_type_key("MRB o/r#9 https://x/pull/9") == "MRB o/r#9"
    assert bw.assign_job_type_key("nothing queued") is None


def test_out_of_fuel_nack_line():
    assert bw.out_of_fuel_nack_line("FR o/r#1") == "NACK FR o/r#1 out-of-fuel"
    assert "out-of-fuel" in bw.out_of_fuel_nack_line("")


def test_ack_miss_tick_ignored_while_out_of_fuel():
    """Supervisor._check_ack_miss must not remind or recycle during out-of-fuel hold."""
    clock = {"t": 0.0}
    logs: list[str] = []
    injects: list[str] = []
    restarts: list[str] = []

    class FakeProc:
        pid = 99

        def poll(self):
            return None

    class FakeIrc:
        shop = "#marchhare"
        alive = True

        def say(self, *a, **k):
            return True

    class FakeRelay:
        on_inject = None
        hold_assigns_while = None
        on_hold_assign = None
        refuse_assign_while = None
        on_refuse_assign = None
        last_unacked = None

        def set_target(self, _t):
            pass

        def hold(self, _m):
            pass

        def release_held_assigns(self):
            return 0

    bored = bw.BoredEmitter(lambda: True, logs.append, harvest_hold_s=0.0)
    bored._out_of_fuel = True
    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=".",
        machine="marchhare",
        nick="marchhare-1",
        run_dir=Path("."),
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        clock=lambda: clock["t"],
        bored=bored,
        detector=bw.HangDetector(not_responding_s=9999, silent_s=9999),
        backoff=(0.0,),
        restart_max=3,
    )
    assign = "FROM Jeeves #marchhare marchhare-1: FR o/r#9 https://example/issues/9"
    sup.ack_miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    sup.ack_miss.note_inject(assign, 0.0, own_nick="marchhare-1")
    sup.proc = FakeProc()
    sup._inject_line = lambda proc, line: injects.append(line) or True  # type: ignore[method-assign]
    sup.restart_agent = lambda reason: restarts.append(reason)  # type: ignore[method-assign]

    clock["t"] = 11.0
    sup._check_ack_miss(sup.proc)
    clock["t"] = 40.0
    sup._check_ack_miss(sup.proc)

    assert injects == []
    assert restarts == []
    assert any("out-of-fuel" in m and "ack-miss" in m for m in logs)


def test_restart_agent_refuses_while_out_of_fuel():
    clock = {"t": 100.0}
    logs: list[str] = []
    kills: list[int] = []

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

    class FakeRelay:
        last_unacked = "FROM Jeeves #m m-1: FR o/r#1 https://x/1"
        on_inject = None
        hold_assigns_while = None
        on_hold_assign = None
        refuse_assign_while = None
        on_refuse_assign = None

        def set_target(self, _t):
            pass

        def hold(self, _m):
            raise AssertionError("must not re-hold assign while out-of-fuel")

        def release_held_assigns(self):
            return 0

    bored = bw.BoredEmitter(lambda: True, logs.append, harvest_hold_s=0.0)
    bored._out_of_fuel = True
    det = bw.HangDetector(not_responding_s=1.0, silent_s=1.0)
    det.note_inject(90.0)
    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=".",
        machine="marchhare",
        nick="marchhare-1",
        run_dir=Path("."),
        irc=None,
        relay=FakeRelay(),
        log=logs.append,
        spawn=lambda spec, env: FakeProc(),
        kill=lambda pid: kills.append(pid) or True,
        probe=lambda pid: bw.Sample(True, True, 1),
        detector=det,
        clock=lambda: clock["t"],
        bored=bored,
        backoff=(0.0,),
        restart_max=3,
        restart_window_s=1800.0,
    )
    sup.proc = FakeProc()
    sup.ack_miss.note_inject(
        "FROM Jeeves #m marchhare-1: FR o/r#1 https://x/1", 90.0, own_nick="marchhare-1"
    )
    sup.restart_agent("no-ack-after-assign")
    assert kills == []
    assert sup.restarts == []
    assert any("out-of-fuel" in m and "no respawn" in m for m in logs)
    # Detector + ack-miss cleared so health_loop cannot keep firing.
    assert det._pending_since is None
    assert sup.ack_miss.tick(clock["t"] + 999.0, ack_open=False) is None


def test_restart_counter_monotonic_across_window():
    """Sliding window must not drop an active restart incident before 3/3."""
    clock = {"t": 0.0}
    logs: list[str] = []
    shutdowns: list[str] = []

    class FakeProc:
        def __init__(self, pid):
            self.pid = pid

        def poll(self):
            return None

    class FakeRelay:
        last_unacked = None
        on_inject = None
        hold_assigns_while = None
        on_hold_assign = None
        refuse_assign_while = None
        on_refuse_assign = None

        def set_target(self, _t):
            pass

        def hold(self, _m):
            pass

        def release_held_assigns(self):
            return 0

    bored = bw.BoredEmitter(lambda: True, logs.append, harvest_hold_s=0.0)
    # Not out of fuel — counter behaviour only.
    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=".",
        machine="marchhare",
        nick="marchhare-1",
        run_dir=Path("."),
        irc=None,
        relay=FakeRelay(),
        log=logs.append,
        spawn=lambda spec, env: FakeProc(9999),
        kill=lambda pid: True,
        probe=lambda pid: bw.Sample(True, True, 1),
        detector=bw.HangDetector(not_responding_s=9999, silent_s=9999),
        clock=lambda: clock["t"],
        bored=bored,
        backoff=(0.0,),
        restart_max=3,
        restart_window_s=1800.0,
    )
    # Stub spawn/restart side effects: only exercise the incident counter.
    sup.start_agent = lambda note="": True  # type: ignore[method-assign]
    sup.shutdown = lambda why, code: shutdowns.append(f"{why}:{code}")  # type: ignore[method-assign]

    # Hangs ~25 min apart: first would age out of a naive per-entry 30 min window
    # (class of ionos 02:32/02:48/03:03). Keep the whole chain so restart 3/3 is
    # reachable; the 4th hang in the same incident gives up (RULE_RESTART_MAX=3).
    for i, t in enumerate((0.0, 1500.0, 3000.0, 4500.0)):
        clock["t"] = t
        sup.proc = FakeProc(1000 + i)
        if i < 3:
            sup.restart_agent("no-ack-after-assign")
            assert len(sup.restarts) == i + 1, (i, sup.restarts)
            assert not shutdowns, shutdowns
        else:
            # At t=4500 the first entry is 75 min old; last is only 25 min old —
            # keep the chain so len already == 3 → give up.
            sup.restart_agent("no-ack-after-assign")
            assert shutdowns, "4th hang in one incident must give up"
            assert any("hang-restart-limit" in s for s in shutdowns)


def test_relay_refuses_assign_while_out_of_fuel_without_inject():
    injected: list[str] = []
    refused: list[str] = []
    logs: list[str] = []

    def inject(line: str) -> bool:
        injected.append(line)
        return True

    relay = bw.Relay(log=logs.append, clock=time.monotonic, max_burst=8, window_s=30.0)
    relay.set_target(inject)
    relay.refuse_assign_while = lambda: True
    relay.on_refuse_assign = lambda line: refused.append(line)

    status = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#4180 https://github.com/SimonBarnett/bobiverse/issues/4180",
    )
    assert status == "out_of_fuel"
    assert injected == []
    assert len(refused) == 1
    assert "4180" in refused[0]
    assert any("out-of-fuel" in m for m in logs)


def test_supervisor_nacks_assign_during_out_of_fuel(tmp_path: Path):
    clock = FakeClock(0.0)
    said: list[str] = []
    logs: list[str] = []

    class FakeIrc:
        shop = "#marchhare"
        alive = True
        on_nak = None
        on_lost = None

        def say(self, target, text):
            said.append(f"{target}:{text}")
            return True

    class FakeProc:
        pid = 7

        def poll(self):
            return None

    e, sent, elogs = _emitter(clock, idle_s=5.0, repeat_s=5.0, harvest_hold_s=0.0)
    # Keep the hold: do not let a live fuel reading clear it mid-test.
    e.fuel_check_fn = lambda: False
    e.out_of_fuel_release_fn = lambda key: None
    e.note_out_of_fuel("402 Payment Required: Grok Build usage balance exhausted")
    assert e.out_of_fuel is True

    relay = bw.Relay(
        log=logs.append,
        clock=clock,
        max_burst=8,
        window_s=30.0,
        persist_dir=tmp_path,
        outbox_path=tmp_path / "outbox.txt",
    )
    relay.set_target(lambda line: True)
    sup = bw.Supervisor(
        kind="grok",
        exe="x",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-1",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=relay,
        log=logs.append,
        bored=e,
        clock=clock,
        spawn=lambda spec, env: FakeProc(),
        kill=lambda pid: True,
        probe=lambda pid: bw.Sample(True, True, 1),
        detector=bw.HangDetector(not_responding_s=9999, silent_s=9999),
        backoff=(0.0,),
    )
    # Supervisor wires fuel_check_fn to a live reader — pin False again for the hold.
    e.fuel_check_fn = lambda: False
    # Wire refuse callbacks the same way Supervisor.__init__ does.
    assert callable(relay.refuse_assign_while)
    assert callable(relay.on_refuse_assign)

    status = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/a-search#1176 https://github.com/SimonBarnett/a-search/issues/1176",
    )
    assert status == "out_of_fuel"
    assert any("NACK FR SimonBarnett/a-search#1176 out-of-fuel" in s for s in said)
    assert e.out_of_fuel is True
    # Still quiet — no !bored from the NACK path (start reason from emitter setup is ok).
    n0 = len(e.sent)
    clock.advance(30.0)
    time.sleep(0.05)
    assert not any(r in ("idle", "nak", "free", "done") for _, r in e.sent[n0:])
    e.stop()


def test_out_of_fuel_then_assign_no_respawn_end_to_end(tmp_path: Path):
    """Wanted deterministic case: 402 GIVEUP, then assign arrives → NACK, no respawn, no !bored."""
    clock = FakeClock(0.0)
    log_path = tmp_path / "unified.jsonl"
    log_path.write_text("", encoding="utf-8")
    said: list[str] = []
    logs: list[str] = []
    injects: list[str] = []
    restarts: list[str] = []

    class FakeIrc:
        shop = "#marchhare"
        alive = True
        on_nak = None
        on_lost = None

        def say(self, target, text):
            said.append(text)
            return True

    class FakeProc:
        pid = 55

        def poll(self):
            return None

    e, sent, elogs = _emitter(clock, idle_s=30.0, repeat_s=30.0, harvest_hold_s=0.0)
    e.fuel_check_fn = lambda: False
    e.on_outbox("ACK FR SimonBarnett/a-search#1176")

    relay = bw.Relay(
        log=logs.append,
        clock=clock,
        max_burst=8,
        window_s=30.0,
        persist_dir=tmp_path,
        outbox_path=tmp_path / "outbox.txt",
    )
    relay.set_target(lambda line: injects.append(line) or True)
    # Patch digest so the real Supervisor release path does not POST.
    import bob_worker as _bw_mod

    _orig_digest = _bw_mod.post_digest_out_of_fuel
    _bw_mod.post_digest_out_of_fuel = lambda **kw: True
    try:
        sup = bw.Supervisor(
            kind="grok",
            exe="x",
            cwd=str(tmp_path),
            machine="marchhare",
            nick="marchhare-11692",
            run_dir=tmp_path,
            irc=FakeIrc(),
            relay=relay,
            log=logs.append,
            bored=e,
            clock=clock,
            spawn=lambda spec, env: FakeProc(),
            kill=lambda pid: True,
            probe=lambda pid: bw.Sample(True, True, 0),
            detector=bw.HangDetector(not_responding_s=1.0, silent_s=1.0),
            backoff=(0.0,),
            restart_max=3,
            restart_window_s=1800.0,
        )
        e.fuel_check_fn = lambda: False
        sup.proc = FakeProc()
        sup.restart_agent = lambda reason: restarts.append(reason)  # type: ignore[method-assign]

        stop = threading.Event()
        hits: list[str] = []

        def on_hit(text: str) -> None:
            hits.append(text)
            # Use Supervisor-wired note_out_of_fuel (GIVEUP via FakeIrc + enter_fn clears).
            e.note_out_of_fuel(text)

        watcher = bw.GrokOutOfFuelWatcher(
            log_path_fn=lambda: log_path,
            on_hit=on_hit,
            stop_event=stop,
            poll_s=0.05,
            log=logs.append,
        )
        th = threading.Thread(target=watcher.run, daemon=True)
        th.start()
        try:
            assert _wait(
                lambda: any("watcher following" in m for m in logs), clock, timeout=2.0
            ), logs
            time.sleep(0.15)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    '{"msg":"402 Payment Required: Grok Build usage balance exhausted"}\n'
                )
                f.flush()
            assert _wait(lambda: len(hits) >= 1, clock, timeout=3.0), (hits, logs)
            assert any(
                s.startswith("GIVEUP FR SimonBarnett/a-search#1176 out-of-fuel") for s in said
            ), said
            assert e.out_of_fuel is True

            # Jeeves offers another job while fuel is exhausted.
            status = relay.deliver(
                "Jeeves",
                "#marchhare",
                "marchhare-11692: FR SimonBarnett/bobiverse#999 https://github.com/SimonBarnett/bobiverse/issues/999",
            )
            assert status == "out_of_fuel"
            assert injects == []
            assert any(
                s.startswith("NACK FR SimonBarnett/bobiverse#999 out-of-fuel") for s in said
            ), said

            # Arm ack-miss as if something slipped through; health must still refuse.
            sup.ack_miss.note_inject(
                "FROM Jeeves #marchhare marchhare-11692: FR o/r#1 https://x/1",
                clock(),
                own_nick="marchhare-11692",
            )
            clock.advance(1000.0)
            sup._check_ack_miss(sup.proc)
            assert restarts == []

            n0 = len(sent)
            clock.advance(120.0)
            time.sleep(0.05)
            assert not any(r in ("idle", "nak", "done-miss", "free") for _, r in e.sent[n0:])
        finally:
            stop.set()
            th.join(timeout=2.0)
            e.stop()
    finally:
        _bw_mod.post_digest_out_of_fuel = _orig_digest


def test_skill_fr4180_documents_ack_miss_hold():
    skill = Path(__file__).resolve().parents[1] / ".grok/skills/bobiverse-bob-worker/SKILL.md"
    raw = skill.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "FR #4180" in t
    assert "ack-miss" in t.lower() or "no-ack-after-assign" in t.lower()
    assert "out-of-fuel" in t.lower()
