# -*- coding: utf-8 -*-
"""FR #9254: OpenCode seat must never twin-ACK two jobs after dual park-worktree.

Incident (redqueen-6148): park MRB #9093 then park FR #9236 while create still
in flight; both ensures finished and both ACK-on-receipt landed in the same
second. Seat-level serialize: one park at a time; cross-job ACK while open
refuses with busy, holding <first>.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as c


ASSIGN_A = (
    "redqueen-1: MRB SimonBarnett/bobiverse#9093 "
    "https://github.com/SimonBarnett/bobiverse/pull/9093"
)
ASSIGN_B = (
    "redqueen-1: FR SimonBarnett/bobiverse#9236 "
    "https://github.com/SimonBarnett/bobiverse/issues/9236"
)
ACK_A = "ACK MRB SimonBarnett/bobiverse#9093"
ACK_B = "ACK FR SimonBarnett/bobiverse#9236"


def _absent_classify(env: dict):
    """Classify that always reports worktree-absent so deliver parks."""

    def classify(line: str) -> str:
        key = bw.assign_job_key(line) or "job"
        nack = f"NACK {key} worktree-absent (FR #6240)"
        assert c.is_worktree_absent_nack(nack)
        return nack

    return classify


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


def test_cross_job_ack_refuse_reason_while_open():
    """ACK open on A → ACK B refused as busy holding A (not duplicate)."""
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK_A)
    assert bored.ack_open is True
    assert bored.outbox_ack_refuse_reason(ACK_A) == "duplicate ACK"
    reason = bored.outbox_ack_refuse_reason(ACK_B)
    assert reason is not None
    assert reason.startswith("busy holding")
    assert "9093" in reason
    assert bored.should_forward_outbox(ACK_B) is False


def test_ack_offer_cross_job_nacks_busy_holding():
    """Deliver B while ACK A is open → NACK busy, holding A; no inject of B."""
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
    relay.turn_busy_other_job = lambda line: bored.live_turn_blocks_assign(line)
    relay.ack_open_job_key = lambda: (
        bored._ack_job_key if bored._ack_open else None
    )

    st1 = relay.deliver("Jeeves", "#redqueen", ASSIGN_A)
    assert st1 == "injected"
    assert outbox == [ACK_A]
    bored.on_outbox(ACK_A)
    # Mark turn open so live_turn_blocks_assign engages (FR #8246).
    with bored._cv:
        bored._turn_open = True

    st2 = relay.deliver("Jeeves", "#redqueen", ASSIGN_B)
    assert st2 in ("busy_turn", "busy_holding", "ack_not_sent", "refused")
    assert not any(x.startswith(ACK_B) or x == ACK_B for x in outbox)
    assert any("busy, holding" in x and "9093" in x for x in outbox), outbox
    assert len(injected) == 1


def test_park_second_job_while_creating_nacks_busy_holding(tmp_path: Path):
    """Second park while first create in flight → NACK busy, holding; no twin ACK."""
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    written: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    gate = threading.Event()
    started = threading.Event()

    def ensure(line: str) -> str:
        started.set()
        gate.wait(timeout=8.0)
        return ""  # ensure "ok" — resume would ACK if we let twin park through

    relay = bw.Relay(log=logs.append, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = _absent_classify(env)
    relay.opencode_ensure_worktree = ensure

    st1 = relay.deliver("jeeves", "#redqueen", ASSIGN_A)
    assert st1 == "opencode_worktree_pending"
    assert started.wait(timeout=2.0)

    st2 = relay.deliver("jeeves", "#redqueen", ASSIGN_B)
    assert st2 in ("busy_holding", "opencode_job_blocked", "busy_turn")
    assert any(
        "busy, holding" in item and "9093" in item for item in written
    ), written
    assert not any(item.startswith("ACK FR") for item in written)

    gate.set()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any(
        item.startswith("ACK MRB") for item in written
    ):
        time.sleep(0.05)
    # First job may ACK after ensure; second must never ACK (avoid matching NACK FR).
    assert not any(
        item.startswith("ACK FR SimonBarnett/bobiverse#9236") for item in written
    )
    assert not any(item.startswith("ACK FR ") for item in written)


def test_resume_after_ensure_nacks_if_other_already_acked(tmp_path: Path):
    """Defense: create finishes after another job already ACK'd → NACK, no twin ACK."""
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    written: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    gate = threading.Event()

    def ensure(line: str) -> str:
        gate.wait(timeout=8.0)
        return ""

    relay = bw.Relay(log=logs.append, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = _absent_classify(env)
    relay.opencode_ensure_worktree = ensure

    # Park B first (will complete after we mark A acked).
    st = relay.deliver("jeeves", "#redqueen", ASSIGN_B)
    assert st == "opencode_worktree_pending"

    # Simulate A already ACK'd on this seat while B's ensure runs.
    key_a = (bw.assign_job_key(ASSIGN_A) or "").strip().lower()
    with relay._lock:
        relay._acked_held_keys.add(key_a)

    gate.set()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any(
        "busy, holding" in item for item in written
    ):
        time.sleep(0.05)
    assert any("busy, holding" in item for item in written), written
    assert not any(item.startswith("ACK FR ") for item in written)
    assert injected == []
