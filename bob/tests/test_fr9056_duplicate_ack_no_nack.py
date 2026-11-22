"""FR #9056: after ACK-on-receipt, re-offer / seat re-ACK must not NACK ack-not-sent.

Repro (marchhare-20584, FR #8798): held assign ACK on receipt -> inject -> seat
re-ACK dropped as stale -> later re-offer hit ACK suppressed (duplicate ACK) and
emitted NACK … ack-not-sent while the seat was still working the job.
"""
from __future__ import annotations

import bob_worker as bw

ASSIGN_A = (
    "FROM Jeeves #marchhare marchhare-1: FR SimonBarnett/bobiverse#8798 "
    "https://github.com/SimonBarnett/bobiverse/issues/8798"
)
ASSIGN_A2 = (
    "FROM Jeeves #marchhare marchhare-1: FR SimonBarnett/bobiverse#8798 "
    "https://github.com/SimonBarnett/bobiverse/issues/8798 [outbox: C:\\x\\outbox.txt]"
)
ACK_A = "ACK FR SimonBarnett/bobiverse#8798"


def _bored(logs=None):
    logs = logs if logs is not None else []
    return bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=lambda: 100.0,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )


def test_duplicate_ack_refuse_reason_while_open():
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK_A)
    assert bored.ack_open is True
    assert bored.outbox_ack_refuse_reason(ACK_A) == "duplicate ACK"
    assert bored.should_forward_outbox(ACK_A) is False


def test_ack_offer_duplicate_is_noop_no_nack():
    """Fail-when: re-offer while same job ACK is open must not write NACK ack-not-sent."""
    outbox: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    bored = _bored(logs)
    bored.set_ready(True)

    relay = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.prepare_offer = lambda line: bored.note_fresh_assign(line)
    relay.ack_refuse_reason = lambda payload: bored.outbox_ack_refuse_reason(payload)

    # First deliver: ACK on receipt + inject.
    st1 = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#8798 "
        "https://github.com/SimonBarnett/bobiverse/issues/8798",
    )
    assert st1 == "injected"
    assert outbox == [ACK_A]
    assert len(injected) == 1
    bored.on_outbox(ACK_A)
    assert bored.ack_open is True

    # Seat re-ACK is refused for IRC (no-op), not a missing ACK.
    assert bored.should_forward_outbox(ACK_A) is False

    # Re-offer with a slightly different footer (new _last_line) while ACK still open.
    st2 = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#8798 "
        "https://github.com/SimonBarnett/bobiverse/issues/8798 [outbox: C:\\x\\outbox.txt]",
    )
    assert st2 == "duplicate"
    assert outbox == [ACK_A], f"must not append NACK ack-not-sent; got {outbox!r}"
    assert len(injected) == 1, "must not re-inject the in-flight job"
    assert not any("ack-not-sent" in x for x in outbox)
    assert any("ACK already open for same job" in m for m in logs), logs


def test_held_reoffer_duplicate_no_nack():
    """Held path: second deliver of same open job after receipt ACK is duplicate, no NACK."""
    outbox: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    bored = _bored(logs)
    bored.set_ready(True)

    relay = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True
    relay.prepare_offer = lambda line: bored.note_fresh_assign(line)
    relay.ack_refuse_reason = lambda payload: bored.outbox_ack_refuse_reason(payload)

    st1 = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#8798 "
        "https://github.com/SimonBarnett/bobiverse/issues/8798",
    )
    assert st1 == "held_until_turn_end"
    assert outbox == [ACK_A]
    bored.on_outbox(ACK_A)

    # Clear last-line dedupe so a footer variant is judged again.
    relay._last_line = ""
    st2 = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#8798 "
        "https://github.com/SimonBarnett/bobiverse/issues/8798 [outbox: C:\\y\\outbox.txt]",
    )
    assert st2 == "duplicate"
    assert outbox == [ACK_A]
    assert injected == []
    assert not any(x.startswith("NACK ") for x in outbox)


def test_finished_job_ack_replay_still_nacks_ack_not_sent():
    """finished-job ACK replay (not duplicate) still refuses with NACK ack-not-sent."""
    outbox: list[str] = []
    logs: list[str] = []
    bored = _bored(logs)
    bored.set_ready(True)
    bored.on_outbox(ACK_A)
    bored.on_outbox(
        "DONE FR SimonBarnett/bobiverse#8798 https://github.com/SimonBarnett/bobiverse/pull/1"
    )
    assert bored.ack_open is False
    assert bored.outbox_ack_refuse_reason(ACK_A) == "finished-job ACK replay"

    relay = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: True)
    # Do not clear finished mark — simulate refuse without prepare_offer clearing.
    relay.prepare_offer = None
    relay.ack_refuse_reason = lambda payload: bored.outbox_ack_refuse_reason(payload)

    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#8798 "
        "https://github.com/SimonBarnett/bobiverse/issues/8798",
    )
    assert st == "ack_not_sent"
    assert any(x == "NACK FR SimonBarnett/bobiverse#8798 ack-not-sent" for x in outbox), outbox
