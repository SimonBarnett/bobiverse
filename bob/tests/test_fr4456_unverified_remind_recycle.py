"""FR #4456: ACK a harvest-held assign on receipt; unverified inject recycles after one verified reminder."""
from __future__ import annotations

import bob_worker as bw


ASSIGN = (
    "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/a-search#2389 "
    "https://github.com/SimonBarnett/a-search/pull/2389"
)


def test_hold_still_parks_and_acks_on_receipt():
    """FR #2811 park stays; FR #4115 ACK is written before any inject."""
    outbox: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda _m: None, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True
    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: MRB SimonBarnett/a-search#2389 https://github.com/SimonBarnett/a-search/pull/2389",
    )
    assert st == "held_until_turn_end"
    assert injected == []
    assert outbox == ["ACK MRB SimonBarnett/a-search#2389"]


def test_unverified_inject_recycles_on_tick_after_first_reminder():
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=900.0)
    miss.note_inject(ASSIGN, 0.0, own_nick="marchhare-1")
    miss.note_unverified()
    assert miss.tick(10.0, ack_open=False) == "remind"
    # Must not wait recycle_s (900) after the unverified reminder.
    assert miss.tick(11.0, ack_open=False) == "recycle"


def test_verified_inject_still_waits_recycle_s():
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    miss.note_inject(ASSIGN, 0.0, own_nick="marchhare-1")
    assert miss.tick(10.0, ack_open=False) == "remind"
    assert miss.tick(11.0, ack_open=False) is None
    assert miss.tick(30.0, ack_open=False) == "recycle"


def test_no_probe_marks_unverified_and_skips_enter():
    enters: list[int] = []
    flags: list[str] = []
    logs: list[str] = []
    ok = bw.inject_with_submit_verify(
        1,
        ASSIGN,
        inject_fn=lambda pid, text, log=None: True,
        enter_fn=lambda pid=0: enters.append(1) or True,
        probe_fn=None,
        clock=lambda: 0.0,
        sleep=lambda _s: None,
        log=logs.append,
        on_unverified=lambda: flags.append("unverified"),
        sync=True,
    )
    assert ok is True
    assert enters == []
    assert flags == ["unverified"]
    assert any("submit-verify skipped (no probe)" in m for m in logs)


def test_force_verify_without_probe_runs_enter_retries():
    enters: list[int] = []
    logs: list[str] = []
    clock = {"t": 0.0}

    def tick() -> float:
        return clock["t"]

    def sleep(s: float) -> None:
        clock["t"] += float(s)

    ok = bw.inject_with_submit_verify(
        1,
        ASSIGN,
        inject_fn=lambda pid, text, log=None: True,
        enter_fn=lambda pid=0: enters.append(1) or True,
        probe_fn=None,
        clock=tick,
        sleep=sleep,
        log=logs.append,
        verify_s=0.2,
        max_retries=2,
        backoffs=(0.2, 0.2),
        force_verify=True,
        sync=True,
    )
    assert ok is True
    assert len(enters) >= 1
    assert any("submit-verify forced (no probe)" in m for m in logs)
    assert any("submit-verify FAILED" in m for m in logs)
