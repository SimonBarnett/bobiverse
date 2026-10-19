"""FR #4858: after agent 402 usage-exhausted, do not clear the out-of-fuel hold
on an optimistic pool reading (pct=3 available).

Hold until min hold expires AND pct is above the clear floor, or a successful
agent turn ends. Unknown / soft mid-job readings without a 402 keep FR #3923.
"""
from __future__ import annotations

import time

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_is_hard_402_out_of_fuel_text():
    assert bw.is_hard_402_out_of_fuel_text(
        "402 Payment Required: Grok Build usage balance exhausted"
    )
    assert bw.is_hard_402_out_of_fuel_text("Grok Build usage balance exhausted")
    assert bw.is_hard_402_out_of_fuel_text(
        'shell.turn.inference_failed status_code=402 "usage balance exhausted"'
    )
    assert not bw.is_hard_402_out_of_fuel_text("NEEDS_AUTH")
    assert not bw.is_hard_402_out_of_fuel_text(
        "mid-job fuel reading exhausted (streak=2)"
    )
    assert not bw.is_hard_402_out_of_fuel_text(
        '{"completion_tokens":402,"prompt_tokens":101459}'
    )


def test_reading_clears_hard_hold_requires_min_hold_and_floor():
    fuel_low = bw.Fuel(grok_pct=3, grok_state="available")
    fuel_ok = bw.Fuel(grok_pct=10, grok_state="available")
    assert not bw.out_of_fuel_reading_clears_hard_hold(
        fuel_low, kind="grok", held_for_s=1.0, min_hold_s=30.0, clear_floor_pct=5
    )
    assert not bw.out_of_fuel_reading_clears_hard_hold(
        fuel_low, kind="grok", held_for_s=60.0, min_hold_s=30.0, clear_floor_pct=5
    )
    assert not bw.out_of_fuel_reading_clears_hard_hold(
        fuel_ok, kind="grok", held_for_s=10.0, min_hold_s=30.0, clear_floor_pct=5
    )
    assert bw.out_of_fuel_reading_clears_hard_hold(
        fuel_ok, kind="grok", held_for_s=60.0, min_hold_s=30.0, clear_floor_pct=5
    )
    # Unknown pct must not clear a hard 402 hold.
    assert not bw.out_of_fuel_reading_clears_hard_hold(
        bw.Fuel(grok_state="available"),
        kind="grok",
        held_for_s=60.0,
        min_hold_s=30.0,
        clear_floor_pct=5,
    )


def test_402_then_pct3_available_stays_held_no_bored():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_min_hold_s = 30.0
    e.out_of_fuel_clear_floor_pct = 5
    e.out_of_fuel_release_fn = lambda key: None

    def check() -> bool:
        at = e._out_of_fuel_at
        held = 0.0 if at is None else float(clock() - at)
        fuel = bw.Fuel(grok_pct=3, grok_state="available")
        ok = bw.out_of_fuel_reading_clears_hard_hold(
            fuel,
            kind="grok",
            held_for_s=held,
            min_hold_s=e.out_of_fuel_min_hold_s,
            clear_floor_pct=e.out_of_fuel_clear_floor_pct,
        )
        if ok:
            e._out_of_fuel_clear_reason = "reading pct=3"
        return ok

    e.fuel_check_fn = check
    e.on_outbox("ACK FR o/r#4858")
    e.note_out_of_fuel(
        "402 Payment Required: Grok Build usage balance exhausted"
    )
    assert e.out_of_fuel is True
    assert e._out_of_fuel_hard_402 is True
    n0 = len(sent)
    clock.advance(60.0)
    time.sleep(0.08)
    assert e.out_of_fuel is True
    assert not any(r in ("idle", "nak", "free", "done") for _, r in e.sent[n0:])
    e.stop()


def test_402_then_pct_above_floor_after_min_hold_clears():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_min_hold_s = 30.0
    e.out_of_fuel_clear_floor_pct = 5
    e.out_of_fuel_release_fn = lambda key: None
    pct = {"v": 3}

    def check() -> bool:
        at = e._out_of_fuel_at
        held = 0.0 if at is None else float(clock() - at)
        fuel = bw.Fuel(grok_pct=pct["v"], grok_state="available")
        ok = bw.out_of_fuel_reading_clears_hard_hold(
            fuel,
            kind="grok",
            held_for_s=held,
            min_hold_s=e.out_of_fuel_min_hold_s,
            clear_floor_pct=e.out_of_fuel_clear_floor_pct,
        )
        if ok:
            e._out_of_fuel_clear_reason = f"reading pct={pct['v']}"
        return ok

    e.fuel_check_fn = check
    e.note_out_of_fuel(
        "402 Payment Required: Grok Build usage balance exhausted"
    )
    clock.advance(35.0)
    time.sleep(0.05)
    assert e.out_of_fuel is True
    pct["v"] = 10
    clock.advance(5.0)
    assert _wait(lambda: e.out_of_fuel is False, clock, timeout=3.0), logs
    assert any("cleared via reading pct=10" in m for m in logs)
    e.stop()


def test_402_successful_turn_clears_before_min_hold():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_min_hold_s = 1800.0
    e.fuel_check_fn = lambda: False
    e.out_of_fuel_release_fn = lambda key: None
    e.note_out_of_fuel(
        "402 Payment Required: Grok Build usage balance exhausted"
    )
    assert e.out_of_fuel is True
    e.turn_ended(at=clock())
    assert e.out_of_fuel is False
    assert any("cleared via successful turn" in m for m in logs)
    e.stop()


def test_soft_mid_job_reading_without_402_still_clears_on_tokens():
    """FR #3923: mid-job exhausted (no hard 402) still clears when grok_has_tokens."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_min_hold_s = 1800.0
    e.out_of_fuel_release_fn = lambda key: None
    e.fuel_check_fn = lambda: True
    e.note_out_of_fuel("mid-job fuel reading exhausted (streak=2)")
    assert e.out_of_fuel is True
    assert e._out_of_fuel_hard_402 is False
    clock.advance(1.0)
    assert _wait(lambda: e.out_of_fuel is False, clock, timeout=3.0), logs
    assert any("cleared via reading" in m for m in logs)
    e.stop()
