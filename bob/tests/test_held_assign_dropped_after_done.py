"""Held assigns for a job the seat already closed (DONE/GIVEUP/NACK) are dropped, never replayed,
and never used as the 'holding X' reason to NACK a new offer (flamingo-11232, a-search #2172 / #2200)."""
from __future__ import annotations

import bob_worker as bw

A = "flamingo-11232: MRB SimonBarnett/a-search#2172 https://github.com/SimonBarnett/a-search/pull/2172"
B = "flamingo-11232: MRB SimonBarnett/a-search#2200 https://github.com/SimonBarnett/a-search/pull/2200"


def _relay():
    outbox, injected, logs = [], [], []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    r.write_outbox = lambda t: outbox.append(t) or True
    r.set_target(lambda line: injected.append(line) or True)
    r.hold_assigns_while = lambda: True
    return r, outbox, injected, logs


def test_done_drops_held_copy_and_next_offer_is_injected_not_nacked():
    r, outbox, injected, logs = _relay()
    assert r.deliver("Jeeves", "#flamingo", A) == "held_until_turn_end"
    # Agent worked #2172 anyway and the seat sent DONE.
    assert r.note_outbound("DONE MRB SimonBarnett/a-search#2172 PASS https://x") == 1
    assert r.deliver("Jeeves", "#flamingo", B) == "held_until_turn_end"
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 1
    assert len(injected) == 1 and "a-search#2200" in injected[0]
    assert not any("#2172" in x for x in injected)
    assert not any(o.startswith("NACK") for o in outbox)


def test_finished_ref_dropped_at_release_even_if_held_after_done():
    r, outbox, injected, logs = _relay()
    r.note_outbound("GIVEUP MRB SimonBarnett/a-search#2172 reason self-MRB")
    r.deliver("Jeeves", "#flamingo", A)
    r.deliver("Jeeves", "#flamingo", B)
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 1
    assert len(injected) == 1 and "a-search#2200" in injected[0]
    assert not any("holding MRB SimonBarnett/a-search#2172" in o for o in outbox)
    assert any("dropped finished held assign" in l for l in logs)


def test_nack_also_drops_and_ack_does_not():
    r, outbox, injected, logs = _relay()
    r.deliver("Jeeves", "#flamingo", A)
    assert r.note_outbound("ACK MRB SimonBarnett/a-search#2172") == 0
    assert r.has_pending_work() is True
    assert r.note_outbound("NACK MRB SimonBarnett/a-search#2172 busy") == 1
    assert r.is_finished_ref(A) is True
    r.hold_assigns_while = lambda: False
    assert r.release_held_assigns() == 0 and injected == []


def test_on_outbox_wire_hooks_relay_note_outbound():
    import inspect
    src = inspect.getsource(bw)
    i = src.index("def on_outbox_wire")
    assert "note_outbound" in src[i:i + 800]
