"""FR #8246: a re-offered job gets a fresh ACK, and a suppressed ACK is not injected."""
from __future__ import annotations

import bob_worker as bw

GIVEUP_X = "GIVEUP MRB SimonBarnett/bobiverse#8224 seat gave up"
ACK_X = "ACK MRB SimonBarnett/bobiverse#8224"
ASSIGN_X = (
    "redqueen-7968: MRB SimonBarnett/bobiverse#8224 "
    "https://github.com/SimonBarnett/bobiverse/pull/8224"
)
ASSIGN_Y = (
    "redqueen-7968: MRB SimonBarnett/bobiverse#8231 "
    "https://github.com/SimonBarnett/bobiverse/pull/8231"
)


def _bored():
    return bw.BoredEmitter(
        lambda: True,
        lambda _m: None,
        clock=lambda: 100.0,
        harvest_hold_s=0.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )


def _wire(bored, outbox, injected):
    relay = bw.Relay(log=lambda _m: None, clock=lambda: 100.0)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.prepare_offer = bored.note_fresh_assign
    relay.ack_refuse_reason = bored.outbox_ack_refuse_reason
    relay.turn_busy_other_job = bored.live_turn_blocks_assign
    relay.on_inject = lambda line: bored.note_fresh_assign(line)
    return relay


def test_reoffer_after_giveup_acks_and_injects():
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK_X)
    bored.on_outbox(GIVEUP_X)
    assert bored.should_forward_outbox(ACK_X) is False
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    result = relay.deliver("jeeves", "#redqueen", ASSIGN_X)
    assert result == "injected"
    assert outbox == [ACK_X]
    assert injected
    assert "bobiverse#8224" in injected[0]
    assert bored.should_forward_outbox(ACK_X) is True
    assert bored.ack_open is False  # drain has not booked the ACK yet
    bored.on_outbox(ACK_X)
    assert bored.ack_open is True


def test_reoffer_while_other_turn_live_nacks_and_does_not_inject():
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox("ACK MRB SimonBarnett/bobiverse#8231")
    bored.turn_started()
    assert bored.turn_open is True
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    result = relay.deliver("jeeves", "#redqueen", ASSIGN_X)
    assert result == "busy_turn"
    assert injected == []
    assert outbox == ["NACK MRB SimonBarnett/bobiverse#8224 busy"]
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/bobiverse#8231"


def test_duplicate_ack_does_not_inject_or_nack():
    """FR #9056: duplicate ACK (already open) is a no-op — no inject, no ack-not-sent."""
    bored = _bored()
    bored.set_ready(True)
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    relay.ack_refuse_reason = lambda _payload: "duplicate ACK"
    result = relay.deliver("jeeves", "#redqueen", ASSIGN_Y)
    assert result == "duplicate"
    assert injected == []
    assert outbox == []


def test_finished_job_ack_replay_still_nacks_ack_not_sent():
    """FR #8246 / #9056: finished-job ACK replay still refuses with NACK ack-not-sent."""
    bored = _bored()
    bored.set_ready(True)
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    relay.ack_refuse_reason = lambda _payload: "finished-job ACK replay"
    result = relay.deliver("jeeves", "#redqueen", ASSIGN_Y)
    assert result == "ack_not_sent"
    assert injected == []
    assert outbox == ["NACK MRB SimonBarnett/bobiverse#8231 ack-not-sent"]
