"""FR #7201: error turn with ACK open retries once, then GIVEUP with a reason."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

KEY = "FR SimonBarnett/bobiverse#7201"


def test_sanitize_failed_turn_reason_redacts_and_keeps_class():
    why = bw.sanitize_failed_turn_reason(
        "PermissionError",
        "The user rejected permission\nsecret ghp_ABCDEFGHIJKLMNOPQRSTUVWX",
    )
    assert why.startswith("PermissionError:")
    assert "ghp_" not in why
    assert "rejected permission" in why.lower() or "rejected" in why.lower()


def test_failed_turn_next_action_retry_then_giveup():
    assert bw.failed_turn_next_action(0) == "retry"
    assert bw.failed_turn_next_action(1) == "giveup"
    line = bw.failed_turn_giveup_line(KEY, "PermissionError", "external_directory auto-rejected")
    assert line.startswith("GIVEUP FR SimonBarnett/bobiverse#7201 failed-turn ")
    assert "PermissionError" in line


def test_error_then_retry_then_success():
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=60.0)
    retries: list[str] = []
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: retries.append(k)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    e.turn_ended(
        at=clock(),
        error=True,
        error_class="PermissionError",
        error_line="The user rejected permission to use this specific tool call.",
    )
    assert retries == [KEY]
    assert giveups == []
    assert e.ack_open is True
    assert any("failed-turn: retry" in m for m in logs), logs
    clock.advance(1.0)
    e.on_outbox("DONE " + KEY + " https://example.com/p/7201")
    assert e.ack_open is False
    assert giveups == []
    e.stop()


def test_error_then_retry_then_error_giveup():
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    retries: list[str] = []
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: retries.append(k)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    err = dict(
        error=True,
        error_class="PermissionError",
        error_line="The user rejected permission to use this specific tool call.",
    )
    e.turn_ended(at=clock(), **err)
    e.turn_ended(at=clock(), **err)
    assert retries == [KEY]
    assert len(giveups) == 1
    assert giveups[0][0] == KEY
    assert giveups[0][1].startswith("failed-turn")
    assert "PermissionError" in giveups[0][1]
    assert e.ack_open is False
    assert any("failed-turn: GIVEUP" in m for m in logs), logs
    e.stop()
