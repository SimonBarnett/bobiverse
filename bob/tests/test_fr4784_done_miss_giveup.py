"""FR #4784: done-miss / ack-stale release must GIVEUP the open ACK before !bored.

Without the shop GIVEUP, Jeeves keeps the accepted row and answers every later
!bored with nak busy (marchhare-10160 / ce-priority MRB #32 for ~60 min).
"""
from __future__ import annotations

import time

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_seat_release_giveup_line_shape():
    assert (
        bw.seat_release_giveup_line("MRB SimonBarnett/ce-priority#32", "done-miss")
        == "GIVEUP MRB SimonBarnett/ce-priority#32 done-miss"
    )
    assert (
        bw.seat_release_giveup_line("MRB o/r#1", "ack-stale")
        == "GIVEUP MRB o/r#1 ack-stale"
    )
    assert bw.seat_release_giveup_line("", "done-miss") == "GIVEUP job done-miss"
    assert bw.seat_release_giveup_line("job", "ack-stale") == "GIVEUP job ack-stale"


def test_done_miss_release_posts_giveup_before_bored():
    """Fail-when: after reminder turn_ended, GIVEUP fires before !bored reason=done-miss."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0, ack_stale_s=2700.0)
    giveups: list[tuple[str, str]] = []
    order: list[str] = []

    def _giveup(job_key: str, reason: str) -> None:
        giveups.append((job_key, reason))
        order.append(f"giveup:{reason}")

    e.seat_release_giveup_fn = _giveup
    e.done_miss_remind_fn = lambda key: None
    # Capture !bored send order relative to giveup.
    orig_send = e.send

    def _send():
        order.append("bored")
        return orig_send()

    e.send = _send  # type: ignore[method-assign]

    e.on_outbox("ACK MRB SimonBarnett/ce-priority#32")
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs), logs
    clock.advance(21.0)
    assert _wait(lambda: e._done_miss_reminded, clock)  # noqa: SLF001
    e.turn_ended(at=clock())  # second end after reminder -> release
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock), e.sent

    assert giveups == [("MRB SimonBarnett/ce-priority#32", "done-miss")], giveups
    assert "giveup:done-miss" in order and "bored" in order, order
    assert order.index("giveup:done-miss") < order.index("bored"), order
    assert any("seat-release: GIVEUP posted" in m for m in logs), logs
    # Local ACK already cleared; shop GIVEUP is what frees Jeeves.
    assert e.ack_open is False
    e.stop()


def test_ack_stale_release_posts_giveup_before_bored():
    """Fail-when: ack-stale release GIVEUPs the open job before !bored reason=ack-stale."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=90.0,
        idle_s=1.0,
        repeat_s=9999.0,
        ack_stale_s=30.0,
        done_miss_grace_s=20.0,
    )
    giveups: list[tuple[str, str]] = []
    order: list[str] = []

    def _giveup(job_key: str, reason: str) -> None:
        giveups.append((job_key, reason))
        order.append(f"giveup:{reason}")

    e.seat_release_giveup_fn = _giveup
    orig_send = e.send

    def _send():
        order.append("bored")
        return orig_send()

    e.send = _send  # type: ignore[method-assign]

    e.on_outbox("ACK MRB SimonBarnett/ce-priority#32")
    e.turn_ended(at=clock())
    clock.advance(1.0)
    e.turn_started(at=clock())
    n0 = len(sent)
    clock.advance(35.0)
    assert _wait(lambda: any(r == "ack-stale" for _, r in e.sent[n0:]), clock), (
        e.sent[n0:],
        logs,
    )
    assert giveups == [("MRB SimonBarnett/ce-priority#32", "ack-stale")], giveups
    assert order.index("giveup:ack-stale") < order.index("bored"), order
    assert e.ack_open is False
    e.stop()


def test_done_miss_without_giveup_fn_still_bored():
    """Giveup callback optional: missing fn must not block !bored release."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=5.0, ack_stale_s=2700.0)
    e.done_miss_remind_fn = lambda key: None
    e.seat_release_giveup_fn = None
    e.on_outbox("ACK MRB o/r#9")
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: e._done_miss_reminded, clock)  # noqa: SLF001
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock), e.sent
    e.stop()
