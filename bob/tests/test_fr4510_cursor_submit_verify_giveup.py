"""FR #4510: Cursor submit-verify FAILED re-pastes once, then GIVEUP."""
from __future__ import annotations

import time

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

ASSIGN = (
    "FROM Jeeves #marchhare marchhare-2176: MRB SimonBarnett/bobiverse#4505 "
    "https://github.com/SimonBarnett/bobiverse/pull/4505"
)
GIVEUP = "GIVEUP MRB SimonBarnett/bobiverse#4505 submit-verify failed"


def _cursor_recovery(*, reinject, acked=True, running=False, cleared=None):
    state = {"outbox": [], "local": [], "input": []}

    def turn_running() -> bool:
        return bool(running() if callable(running) else running)

    rec = bw.InjectRecovery(
        reinject=reinject,
        write_outbox=lambda text: state["outbox"].append(text) or True,
        clear_local=lambda line: state["local"].append(line),
        is_acked=lambda line: acked,
        log=lambda m: None,
        giveup_on_fail=True,
        block_on_receipt_ack=False,
        turn_running=turn_running,
        clear_input=lambda: state["input"].append("cleared"),
    )
    if cleared is not None:
        state["input"] = cleared
    return rec, state


def test_repaste_success_sends_no_giveup_even_when_receipt_acked():
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        return True

    rec, state = _cursor_recovery(reinject=reinject, acked=True)
    assert rec.on_failed(ASSIGN, attempt=1) == "retried"
    assert pasted == [ASSIGN]
    assert state["outbox"] == []
    # FR #4842: clear queued TUI input before re-paste (stale assign must not win).
    assert state["input"] == ["cleared"]


def test_both_attempts_fail_sends_one_giveup_and_clears_input():
    def reinject(line, cb):
        cb()
        return True

    rec, state = _cursor_recovery(reinject=reinject, acked=True)
    rec.on_failed(ASSIGN, attempt=1)
    assert state["outbox"] == [GIVEUP]
    # clear before re-paste (FR #4842) + clear on giveup (FR #4510)
    assert state["input"] == ["cleared", "cleared"]
    assert state["local"] == [ASSIGN]
    # A second failure for the same job must not send another GIVEUP.
    assert rec.on_failed(ASSIGN, attempt=2) == "giveup"
    assert state["outbox"] == [GIVEUP]


def test_no_giveup_while_a_turn_is_running():
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        return True

    rec, state = _cursor_recovery(reinject=reinject, running=True)
    assert rec.on_failed(ASSIGN, attempt=1) == "running"
    assert pasted == []
    assert state["outbox"] == []
    assert state["input"] == []


def test_giveup_releases_the_ack_and_bored_waits_for_the_harvest_hold():
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, turn_hold_max_s=600.0)
    e.set_ready(True)
    assert _wait(lambda: len(sent) == 1, clock)
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#4505")
    assert e.ack_open is True
    n0 = len(sent)
    e.on_outbox(GIVEUP)
    assert e.ack_open is False
    clock.advance(89.0)
    time.sleep(0.05)
    assert len(sent) == n0, "must not !bored before the harvest hold ends"
    clock.advance(2.0)
    assert _wait(lambda: len(sent) > n0, clock)
    assert e.sent[-1][1] == "free"
    assert any("free-rx matched (GIVEUP)" in m for m in logs)
    e.stop()
