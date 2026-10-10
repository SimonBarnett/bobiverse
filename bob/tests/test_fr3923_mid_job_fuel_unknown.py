"""FR #3923: mid-job fuel check must not treat unknown/transient readings as exhausted.

Acceptance:
(a) helper timeout / empty Fuel while ACK open → no GIVEUP
(b) one transient 0 then recovery → no GIVEUP
(c) two consecutive explicit 0 / exhausted readings → GIVEUP
"""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_fuel_explicitly_exhausted_unknown_is_not_lost():
    empty = bw.Fuel()
    assert bw.fuel_reading_known(empty, "grok") is False
    assert bw.fuel_explicitly_exhausted(empty, "grok") is False
    assert bw.fuel_reading_known(empty, "cursor") is False
    assert bw.fuel_explicitly_exhausted(empty, "cursor") is False


def test_fuel_explicitly_exhausted_grok_pct_zero_and_state():
    assert bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=0, grok_state="exhausted"), "grok")
    assert bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=0, grok_state="unknown"), "grok")
    assert bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=None, grok_state="exhausted"), "grok")
    assert not bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=84, grok_state="available"), "grok")
    assert not bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=None, grok_state="available"), "grok")
    assert not bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=None, grok_state="unknown"), "grok")


def test_fuel_explicitly_exhausted_cursor_pools():
    assert bw.fuel_explicitly_exhausted(bw.Fuel(cursor_high=0, cursor_low=0), "cursor")
    assert bw.fuel_explicitly_exhausted(bw.Fuel(cursor_high=0, cursor_low=None), "cursor")
    assert not bw.fuel_explicitly_exhausted(bw.Fuel(cursor_high=12, cursor_low=0), "cursor")
    assert not bw.fuel_explicitly_exhausted(bw.Fuel(), "cursor")


def test_a_unknown_fuel_while_ack_open_no_giveup(monkeypatch):
    """(a) helper returns empty Fuel (timeout / unreadable) → no GIVEUP."""
    clock = FakeClock(0.0)
    released: list[str] = []
    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.fuel_lost_check_fn = lambda: bw.fuel_explicitly_exhausted(bw.Fuel(), "grok")
    e.on_outbox("ACK MRB o/r#3923")
    clock.advance(1.0)
    for _ in range(4):
        clock.advance(5.5)
        time.sleep(0.05)
    assert released == []
    assert e.out_of_fuel is False
    assert e.ack_open is True
    e.stop()


def test_b_transient_zero_then_recovery_no_giveup():
    """(b) one explicit 0 then 84 → streak resets, no GIVEUP."""
    clock = FakeClock(0.0)
    released: list[str] = []
    readings = [
        bw.Fuel(grok_pct=0, grok_state="exhausted"),
        bw.Fuel(grok_pct=84, grok_state="available"),
        bw.Fuel(grok_pct=84, grok_state="available"),
    ]
    idx = {"n": 0}

    def fuel_lost() -> bool:
        i = min(idx["n"], len(readings) - 1)
        f = readings[i]
        idx["n"] += 1
        return bw.fuel_explicitly_exhausted(f, "grok")

    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.fuel_lost_check_fn = fuel_lost
    e.on_outbox("ACK MRB o/r#3923b")
    clock.advance(1.0)
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    assert e.ack_open is True
    e.stop()


def test_c_two_consecutive_exhausted_giveup():
    """(c) two consecutive explicit 0 readings → GIVEUP."""
    clock = FakeClock(0.0)
    released: list[str] = []
    n = {"n": 0}

    def fuel_lost() -> bool:
        n["n"] += 1
        return bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=0, grok_state="exhausted"), "grok")

    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.fuel_lost_check_fn = fuel_lost
    e.on_outbox("ACK MRB o/r#3923")
    clock.advance(1.0)
    # First exhausted poll: streak=1, hold.
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    assert e.ack_open is True
    # Second consecutive exhausted poll: GIVEUP.
    clock.advance(5.5)
    assert _wait(lambda: len(released) == 1, clock, timeout=3.0), (released, logs, n)
    assert released == ["GIVEUP MRB o/r#3923 out-of-fuel"]
    assert e.out_of_fuel is True
    assert any("mid-job fuel reading exhausted" in m for m in logs)
    assert any("streak=2" in m or "consecutive" in m.lower() for m in logs)
    e.stop()


def test_fuel_lost_mid_job_unknown_false(monkeypatch, tmp_path: Path):
    """Supervisor._fuel_lost_mid_job: empty read_fuel must not report lost."""
    class Seat:
        kind = "grok"
        secret = None
        def _install_root_for_fuel(self):
            return tmp_path
        def log(self, msg: str) -> None:
            self.logs.append(msg)

    seat = Seat()
    seat.logs = []
    monkeypatch.setattr(bw, "read_fuel", lambda *a, **kw: bw.Fuel())
    assert bw.Supervisor._fuel_lost_mid_job(seat) is False
    assert any("unknown" in m.lower() or "pct=None" in m or "state=unknown" in m for m in seat.logs)


def test_fuel_lost_mid_job_explicit_zero(monkeypatch, tmp_path: Path):
    class Seat:
        kind = "grok"
        secret = None
        def _install_root_for_fuel(self):
            return tmp_path
        def log(self, msg: str) -> None:
            self.logs.append(msg)

    seat = Seat()
    seat.logs = []
    monkeypatch.setattr(
        bw, "read_fuel", lambda *a, **kw: bw.Fuel(grok_pct=0, grok_state="exhausted")
    )
    assert bw.Supervisor._fuel_lost_mid_job(seat) is True
    assert any("pct=0" in m for m in seat.logs)
