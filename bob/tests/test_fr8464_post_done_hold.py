"""FR #8464: after DONE, an open turn parks the next assign instead of NACK busy."""
from __future__ import annotations

import bob_worker as bw

ACK = "ACK MRB SimonBarnett/bobiverse#8451"
DONE = "DONE MRB SimonBarnett/bobiverse#8451 https://github.com/SimonBarnett/bobiverse/pull/8451"
ASSIGN_NEXT = (
    "flamingo-14448: MRB SimonBarnett/bobiverse#8455 "
    "https://github.com/SimonBarnett/bobiverse/pull/8455"
)
ASSIGN_OTHER = (
    "flamingo-14448: MRB SimonBarnett/bobiverse#8450 "
    "https://github.com/SimonBarnett/bobiverse/pull/8450"
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
    relay.hold_assigns_while = lambda: True
    relay.on_inject = lambda line: bored.note_fresh_assign(line)
    return relay


def test_fr8464_done_open_turn_holds_next_assign():
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK)
    bored.turn_started()
    bored.on_outbox(DONE)
    assert bored.ack_open is False
    assert bored.turn_open is True
    assert bored.live_turn_blocks_assign(ASSIGN_NEXT) is False
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    result = relay.deliver("jeeves", "#flamingo", ASSIGN_NEXT)
    assert result == "held_until_turn_end"
    assert injected == []
    assert not any(line.startswith("NACK ") for line in outbox)


def test_fr8464_mid_job_other_assign_still_nacks_busy():
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK)
    bored.turn_started()
    assert bored.ack_open is True
    assert bored.live_turn_blocks_assign(ASSIGN_OTHER) is True
    outbox: list[str] = []
    injected: list[str] = []
    relay = _wire(bored, outbox, injected)
    result = relay.deliver("jeeves", "#flamingo", ASSIGN_OTHER)
    assert result == "busy_turn"
    assert injected == []
    assert outbox == ["NACK MRB SimonBarnett/bobiverse#8450 busy"]
