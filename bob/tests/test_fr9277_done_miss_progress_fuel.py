# -*- coding: utf-8 -*-
"""FR #9277: done-miss must not fire while progress advances; paid-go unknown is not fuel spam."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

GO_MODEL = "opencode-go/deepseek-v4-pro"


def test_fr9277_progress_after_turn_ended_cancels_done_miss_before_remind(tmp_path: Path):
    """False turn_ended while streaming: progress heartbeat cancels armed done-miss."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK FR SimonBarnett/bobiverse#9236")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs), logs
    # Progress heartbeat / I/O after the false turn_ended (same ACK).
    clock.advance(5.0)
    e.note_agent_active(at=clock())
    assert any("done-miss: cancelled" in m for m in logs), logs
    clock.advance(30.0)
    time.sleep(0.05)
    assert reminds == []
    assert e.ack_open is True
    assert not any(r == "done-miss" for _, r in e.sent)
    e.stop()


def test_fr9277_fire_remind_skips_when_progress_after_arm(tmp_path: Path):
    """Even without note_agent_active clearing state, remind path sees later activity."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK FR o/r#9277")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    # Simulate activity stamped after arm without going through note_agent_active clear
    # (race: activity recorded, then remind due). Directly set active after arm.
    with e._cv:
        armed = e._done_miss_armed_at
        assert armed is not None
        e._agent_active_at = float(armed) + 1.0
    clock.advance(25.0)
    assert _wait(lambda: any("cancelled" in m and "done-miss" in m for m in logs), clock)
    assert reminds == []
    e.stop()


def test_fr9277_real_quiet_turn_end_still_reminds(tmp_path: Path):
    """No progress after turn_ended → done-miss remind still fires (regression)."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.on_outbox("ACK FR o/r#9277b")
    clock.advance(10.0)
    e.turn_ended(at=clock())
    clock.advance(25.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    e.stop()


def test_fr9277_paid_go_unknown_midjob_not_lost_and_quiet_log(tmp_path: Path, monkeypatch):
    """Paid go seat with go=None / free=0 must not count as exhausted or spam out-of-fuel."""
    fuel = bw.Fuel(opencode_free=0, opencode_go=None, grok_pct=91, grok_state="available")
    assert bw.fuel_reading_known(fuel, "opencode", start_model=GO_MODEL) is False
    assert bw.fuel_explicitly_exhausted(fuel, "opencode", start_model=GO_MODEL) is False

    logs: list[str] = []
    bored = MagicMock()
    bored.out_of_fuel = False
    bored._out_of_fuel_hard_402 = False
    bored.clock = lambda: 0.0

    class _Sup:
        kind = "opencode"
        last_child_env = {"BOB_WORKER_ACTUAL_MODEL": GO_MODEL}
        base_env = {}
        secret = None
        _fleet_fuel_hold = None
        _last_midjob_fuel_snap = None
        _midjob_unknown_logged = False

        def _install_root_for_fuel(self):
            return tmp_path

    monkeypatch.setattr(
        bw,
        "take_midjob_fuel",
        lambda *a, **k: (fuel, "", None, None),
    )
    monkeypatch.setattr(
        bw,
        "launched_hostile_start_model",
        lambda kind, env=None: GO_MODEL,
    )
    monkeypatch.setattr(bw, "fold_opencode_seat_pauses", lambda f, *a, **k: f)

    sup = _Sup()
    sup.bored = bored
    sup.log = logs.append
    lost = bw.Supervisor._fuel_lost_mid_job(sup)
    assert lost is False
    # Must not use out-of-fuel: prefix for unknown paid-go (spam class of redqueen-6148).
    assert not any(m.startswith("out-of-fuel: mid-job reading") for m in logs), logs
    assert any("fuel: mid-job" in m and "known=False" in m for m in logs), logs
    # Second identical poll stays quiet (no spam).
    n = len(logs)
    lost2 = bw.Supervisor._fuel_lost_mid_job(sup)
    assert lost2 is False
    assert len(logs) == n


def test_fr9277_paid_go_zero_still_logs_out_of_fuel_prefix(tmp_path: Path, monkeypatch):
    """Explicit go=0 remains a real mid-job exhausted reading (log + lost)."""
    fuel = bw.Fuel(opencode_free=100, opencode_go=0)
    logs: list[str] = []

    class _Sup:
        kind = "opencode"
        last_child_env = {"BOB_WORKER_ACTUAL_MODEL": GO_MODEL}
        base_env = {}
        secret = None
        _fleet_fuel_hold = None
        _last_midjob_fuel_snap = None
        _midjob_unknown_logged = False

        def _install_root_for_fuel(self):
            return tmp_path

    monkeypatch.setattr(
        bw,
        "take_midjob_fuel",
        lambda *a, **k: (fuel, "", None, None),
    )
    monkeypatch.setattr(
        bw,
        "launched_hostile_start_model",
        lambda kind, env=None: GO_MODEL,
    )
    monkeypatch.setattr(bw, "fold_opencode_seat_pauses", lambda f, *a, **k: f)

    sup = _Sup()
    sup.bored = MagicMock()
    sup.log = logs.append
    lost = bw.Supervisor._fuel_lost_mid_job(sup)
    assert lost is True
    assert any(m.startswith("out-of-fuel: mid-job reading") for m in logs), logs
