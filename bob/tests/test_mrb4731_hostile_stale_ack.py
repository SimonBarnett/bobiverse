"""MRB #4731: pin FR #4730 stale-ACK drop + re-offer clear on main."""
from __future__ import annotations

import bob_worker as bw


def test_finished_ack_is_dropped_before_irc_and_reoffer_clears():
    logs: list[str] = []
    bored = bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=lambda: 1.0,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )
    bored.set_ready(True)
    ack = "ACK MRB SimonBarnett/a-search#4370"
    done = "DONE MRB SimonBarnett/a-search#4370 PASS https://example.test/p"
    assign = (
        "n: MRB SimonBarnett/a-search#4370 "
        "https://github.com/SimonBarnett/a-search/pull/4370"
    )
    bored.on_outbox(ack)
    bored.on_outbox(done)
    assert bored.should_forward_outbox(ack) is False
    assert "ignore stale ACK" in "\n".join(logs) or bored.ack_open is False
    bored.note_fresh_assign(assign)
    assert bored.should_forward_outbox(ack) is True


def test_source_pins_fr4730_needles():
    src = open(bw.__file__, encoding="utf-8").read()
    assert "FR #4730" in src
    assert "ignore stale ACK" in src
    assert "dropped stale replay" in src
    assert "note_fresh_assign" in src
    assert "_finished_job_keys" in src
    assert "may_send_outbox" in src
