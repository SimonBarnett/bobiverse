"""FR #2996: after done-miss release, stale _release_gen must not silence !bored or spin CPU.

Repro (ionos win-mpre8vi4u6u-20088): a prior normal turn-end release sets _release_gen;
done-miss release left gens unequal so _reason gated forever and _run wait(0)-spun.
"""
from __future__ import annotations

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_fr2996_nak_idle_after_done_miss_following_prior_turn_end_release():
    """Prior DONE turn-end + later done-miss must still allow nak/idle !bored."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=5.0,
        done_miss_grace_s=20.0,
        idle_s=120.0,
        repeat_s=180.0,
        nak_s=1.0,
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)

    # 1) Normal DONE + turn_ended release (sets _release_gen == _turn_gen).
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#1")
    e.on_outbox("DONE MRB o/r#1 FAIL https://example.com/pull/1")
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in e.sent), clock), (e.sent, logs)

    # 2) New assign → done-miss arm → reminder → release turn.
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#2994")
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs), logs
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock), (reminds, logs)
    e.turn_started(at=clock())  # reminder inject turn
    clock.advance(1.0)
    n0 = len(sent)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent[n0:]), clock), (e.sent[n0:], logs)
    assert e._release_gen == e._turn_gen, (
        f"stale release_gen after done-miss: release={e._release_gen} turn={e._turn_gen}"
    )

    # 3) nothing-queued NAK path must fire (was [] with gens (1, 3) on main 153af99).
    n1 = len(sent)
    e.nak()
    clock.advance(1.2)
    assert _wait(
        lambda: any(r in ("nak", "idle") for _, r in e.sent[n1:]),
        clock,
        timeout=3.0,
    ), (e.sent[n1:], e._release_gen, e._turn_gen)
    e.stop()


def test_fr2996_control_done_miss_without_prior_release_still_naks():
    """Baseline: first-lifetime done-miss (release_gen was None) already worked."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=5.0,
        done_miss_grace_s=20.0,
        idle_s=120.0,
        repeat_s=180.0,
        nak_s=1.0,
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#2994")
    e.turn_ended(at=clock())
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock), (reminds, logs)
    e.turn_started(at=clock())
    n0 = len(sent)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent[n0:]), clock)
    n1 = len(sent)
    e.nak()
    clock.advance(1.2)
    assert _wait(lambda: any(r in ("nak", "idle") for _, r in e.sent[n1:]), clock, timeout=3.0)
    e.stop()


def test_fr2996_run_clamps_past_due_wait():
    """Defensive: _run must not busy-wait when due is already past and reason is None."""
    from pathlib import Path

    text = Path(bw.__file__).read_text(encoding="utf-8-sig")
    run_body = text.split("def _run(self)")[1].split("STALE_BUILD")[0]
    assert "FR #2996" in run_body
    assert "0.5" in run_body
