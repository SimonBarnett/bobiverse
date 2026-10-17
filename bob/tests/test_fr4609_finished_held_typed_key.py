"""FR #4609: finished held-assign match is typed ``TYPE owner/repo#N``.

DONE FIX must not silence a later held MRB for the same number; dropping an
ACKed held assign must emit NACK so Jeeves never keeps a ghost ACK.
"""
from __future__ import annotations

import bob_worker as bw

FIX_DONE = "DONE FIX SimonBarnett/a-search#2366 https://github.com/SimonBarnett/a-search/pull/2366"
MRB_ASSIGN = (
    "flamingo-70260: MRB SimonBarnett/a-search#2366 "
    "https://github.com/SimonBarnett/a-search/pull/2366"
)
MRB_DONE = "DONE MRB SimonBarnett/a-search#2366 PASS https://github.com/SimonBarnett/a-search/pull/2366"
OTHER_MRB = (
    "flamingo-70260: MRB SimonBarnett/a-search#2177 "
    "https://github.com/SimonBarnett/a-search/pull/2177"
)


def _relay():
    outbox, injected, logs = [], [], []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    r.write_outbox = lambda t: outbox.append(t) or True
    r.set_target(lambda line: injected.append(line) or True)
    r.hold_assigns_while = lambda: True
    return r, outbox, injected, logs


def test_done_fix_does_not_finish_held_mrb_same_number():
    """Acceptance: DONE FIX X#N then held MRB X#N at turn end → inject MRB (not silent drop)."""
    r, outbox, injected, logs = _relay()
    assert r.note_outbound(FIX_DONE) == 0  # nothing held yet; records FIX typed key
    assert r.deliver("Jeeves", "#flamingo", MRB_ASSIGN) == "held_until_turn_end"
    assert "ACK MRB SimonBarnett/a-search#2366" in outbox
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 1
    assert len(injected) == 1 and "MRB SimonBarnett/a-search#2366" in injected[0]
    assert not any("dropped finished held assign" in l for l in logs)
    assert not any(o.startswith("NACK MRB SimonBarnett/a-search#2366") for o in outbox)


def test_done_mrb_still_drops_held_mrb_same_key():
    """Same typed key: DONE MRB drops a held MRB copy (no ghost inject)."""
    r, outbox, injected, logs = _relay()
    assert r.deliver("Jeeves", "#flamingo", MRB_ASSIGN) == "held_until_turn_end"
    assert r.note_outbound(MRB_DONE) == 1
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 0
    assert injected == []


def test_prior_done_mrb_then_new_mrb_offer_nacks_not_silent_drop():
    """Same typed key still finished: drop at release but NACK the prior ACK (no ghost busy)."""
    r, outbox, injected, logs = _relay()
    r.note_outbound(MRB_DONE)
    assert r.is_finished_ref(MRB_ASSIGN) is True
    assert r.deliver("Jeeves", "#flamingo", MRB_ASSIGN) == "held_until_turn_end"
    assert "ACK MRB SimonBarnett/a-search#2366" in outbox
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 0
    assert injected == []
    assert any("dropped finished held assign" in l for l in logs)
    assert any(o.startswith("NACK MRB SimonBarnett/a-search#2366") for o in outbox), outbox


def test_dropped_acked_finished_held_emits_nack():
    """Acceptance: if a finished held assign is dropped after ACK-on-receipt, emit NACK."""
    r, outbox, injected, logs = _relay()
    # Seed finished without clearing path: hold, then mark finished without note_outbound drop
    # (simulate typed key still finished when release runs — e.g. race). Force via note then
    # re-hold without going through clear: use raw finished set after ACK.
    assert r.deliver("Jeeves", "#flamingo", MRB_ASSIGN) == "held_until_turn_end"
    assert "ACK MRB SimonBarnett/a-search#2366" in outbox
    # Manually re-mark finished after ACK (belt path): note_outbound on DONE while still pending
    # already dropped pending in normal flow; here re-add pending + finished.
    with r._lock:
        r._finished_refs.add("mrb simonbarnett/a-search#2366")
        if MRB_ASSIGN not in r._pending:
            r._pending.append(MRB_ASSIGN)
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 0
    assert injected == []
    assert any("dropped finished held assign" in l for l in logs)
    assert any(
        o.startswith("NACK MRB SimonBarnett/a-search#2366") for o in outbox
    ), outbox


def test_outbox_job_key_includes_fix():
    assert bw.outbox_job_key(FIX_DONE) == "FIX SimonBarnett/a-search#2366"
    assert bw.outbox_job_key(MRB_DONE) == "MRB SimonBarnett/a-search#2366"


def test_done_fix_does_not_nack_unrelated_held_mrb():
    r, outbox, injected, logs = _relay()
    r.note_outbound(FIX_DONE)
    assert r.deliver("Jeeves", "#flamingo", OTHER_MRB) == "held_until_turn_end"
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 1
    assert "#2177" in injected[0]
