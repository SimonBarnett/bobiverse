# -*- coding: utf-8 -*-
"""FR #9339: MRB re-offer after prior DONE must not NACK already finished.

Acceptance (a): FAIL on old head, then FIX push / re-offer → inject for review.
(c) covered elsewhere when finished without a fresh ACK path still NACKs.
"""
from __future__ import annotations

import bob_worker as bw

MRB_ASSIGN = (
    "flamingo-70260: MRB SimonBarnett/bobiverse#9287 "
    "https://github.com/SimonBarnett/bobiverse/pull/9287"
)
MRB_DONE_FAIL = (
    "DONE MRB SimonBarnett/bobiverse#9287 FAIL "
    "https://github.com/SimonBarnett/bobiverse/pull/9287"
)


def _relay():
    outbox, injected, logs = [], [], []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    r.write_outbox = lambda t: outbox.append(t) or True
    r.set_target(lambda line: injected.append(line) or True)
    r.hold_assigns_while = lambda: True
    return r, outbox, injected, logs


def test_fr9339_reoffer_after_done_clears_finished_and_injects():
    """S1(a): prior DONE FAIL then new MRB assign → clear finished; inject (no already finished NACK)."""
    r, outbox, injected, logs = _relay()
    r.note_outbound(MRB_DONE_FAIL)
    assert r.is_finished_ref(MRB_ASSIGN) is True
    # Fresh offer path clears finished mark (FR #9339) then ACK-on-receipt.
    assert r.deliver("Jeeves", "#flamingo", MRB_ASSIGN) == "held_until_turn_end"
    assert r.is_finished_ref(MRB_ASSIGN) is False
    assert "ACK MRB SimonBarnett/bobiverse#9287" in outbox
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 1
    assert len(injected) == 1 and "MRB SimonBarnett/bobiverse#9287" in injected[0]
    assert not any(
        o.startswith("NACK MRB SimonBarnett/bobiverse#9287") and "already finished" in o
        for o in outbox
    ), outbox


def test_fr9339_clear_finished_ref_helper():
    r, outbox, injected, logs = _relay()
    r.note_outbound(MRB_DONE_FAIL)
    assert r.is_finished_ref(MRB_ASSIGN) is True
    r.clear_finished_ref(MRB_ASSIGN)
    assert r.is_finished_ref(MRB_ASSIGN) is False
