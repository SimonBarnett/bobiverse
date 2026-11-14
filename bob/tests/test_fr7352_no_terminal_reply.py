"""FR #7352: silent turn after ACK -> one reminder, then GIVEUP no-terminal-reply + !bored."""
from __future__ import annotations

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_fr7352_giveup_line_uses_no_terminal_reply():
    assert (
        bw.seat_release_giveup_line("MRB SimonBarnett/bobiverse#7311", "no-terminal-reply")
        == "GIVEUP MRB SimonBarnett/bobiverse#7311 no-terminal-reply"
    )


def test_fr7352_silent_reminder_turn_giveup_and_bored(tmp_path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    giveups: list[tuple[str, str]] = []
    e, sent, logs = _emitter(
        clock, harvest_hold_s=90.0, done_miss_grace_s=20.0, done_miss_reply_s=30.0
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#7311")
    e.turn_ended(at=clock())
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock)
    assert giveups == [("MRB SimonBarnett/bobiverse#7311", "no-terminal-reply")]
    assert e.ack_open is False
    assert not any("DONE MRB" in m for m in logs)
    e.stop()


def test_fr7352_no_second_turn_timeout_giveup(tmp_path):
    """Reminder injected but agent never starts another turn (marchhare-28732 class)."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    giveups: list[tuple[str, str]] = []
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=90.0,
        done_miss_grace_s=5.0,
        done_miss_reply_s=20.0,
        ack_stale_s=2700.0,
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#7311")
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    clock.advance(21.0)
    assert _wait(lambda: giveups == [("MRB SimonBarnett/bobiverse#7311", "no-terminal-reply")], clock)
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock)
    assert e.ack_open is False
    assert clock() < 2700.0
    e.stop()


def test_fr7352_terminal_reply_during_reminder_stops_escalation(tmp_path):
    clock = FakeClock(0.0)
    reminds: list[str] = []
    giveups: list[tuple[str, str]] = []
    e, sent, logs = _emitter(
        clock, harvest_hold_s=5.0, done_miss_grace_s=5.0, done_miss_reply_s=60.0
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK MRB o/r#7311")
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: len(reminds) == 1, clock)
    e.on_outbox("GIVEUP MRB o/r#7311 harvest")
    clock.advance(30.0)
    assert giveups == []
    assert not any(r == "done-miss" for _, r in e.sent)
    assert e.ack_open is False
    e.stop()
