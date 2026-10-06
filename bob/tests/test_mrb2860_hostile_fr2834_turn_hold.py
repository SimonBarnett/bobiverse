"""MRB #2860 hostile pins for FR #2834 open-turn harvest hold extension."""
from __future__ import annotations

import os
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


ROOT = Path(__file__).resolve().parents[1]


def test_mrb2860_skill_cites_fr2834_turn_hold_max_contiguous():
    text = (ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(encoding="utf-8")
    assert "FR #2834" in text
    assert "BOB_WORKER_TURN_HOLD_MAX_S" in text
    assert "keep holding past `harvest_hold_s` until `turn_ended` or `BOB_WORKER_TURN_HOLD_MAX_S`" in text
    assert (
        "do not fire harvest_hold_s !bored (or stale-build recycle) until turn_ended or TURN_HOLD_MAX_S (FR #2834)"
        in text
    )


def test_mrb2860_busy_and_holding_true_past_harvest_while_turn_open():
    clock = FakeClock(0.0)
    e, sent, _ = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.on_outbox("DONE FR o/r#2834 https://example.com/p/2834")
    n0 = len(sent)
    clock.advance(95.0)
    assert e.holding_incoming_assigns is True
    assert e._busy(clock()) is True
    assert len(sent) == n0, "must not !bored while turn open past harvest_hold_s"
    e.stop()


def test_mrb2860_opt_out_bored_on_turn_end_uses_harvest_hold_only():
    """BOB_WORKER_BORED_ON_TURN_END=0: open turn must not extend past harvest_hold_s."""
    old = os.environ.get("BOB_WORKER_BORED_ON_TURN_END")
    os.environ["BOB_WORKER_BORED_ON_TURN_END"] = "0"
    try:
        assert bw.bored_on_turn_end_enabled() is False
        clock = FakeClock(0.0)
        e, sent, _ = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
        e.turn_started(at=clock())
        clock.advance(1.0)
        e.on_outbox("DONE FR o/r#9 https://example.com/p/9")
        n0 = len(sent)
        clock.advance(92.0)
        assert _wait(lambda: len(sent) > n0, clock)
        assert e.sent[-1][1] == "done"
        e.stop()
    finally:
        if old is None:
            os.environ.pop("BOB_WORKER_BORED_ON_TURN_END", None)
        else:
            os.environ["BOB_WORKER_BORED_ON_TURN_END"] = old
