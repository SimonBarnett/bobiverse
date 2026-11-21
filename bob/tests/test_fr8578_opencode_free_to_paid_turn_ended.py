"""FR #8578: free-to-paid switch must not stamp terminal out-of-fuel turn_ended."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter

KEY = "FR SimonBarnett/bobiverse#8578"


def test_fr8578_is_failed_turn_fuel_error_skips_free_to_paid_switch():
    assert bw.is_failed_turn_fuel_error("free-to-paid-switch", "") is False
    assert (
        bw.is_failed_turn_fuel_error(
            "free-to-paid-switch",
            "exit 1: Free usage limit reached. Subscribe to OpenCode Go",
        )
        is False
    )
    assert bw.is_failed_turn_fuel_error("out-of-fuel", "exit 1: Free usage") is True


def test_fr8578_bored_emitter_keeps_ack_on_free_to_paid_switch():
    clock = FakeClock(time.time())
    e, _sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: None
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    # Non-error marker (wrapper clears status/err for FR #8578).
    e.turn_ended(
        at=clock(),
        error=False,
        error_class="free-to-paid-switch",
        error_line="",
    )
    assert giveups == []
    assert e.ack_open is True
    assert not any("failed-turn: GIVEUP" in m for m in logs), logs
    e.stop()


def test_fr8578_bored_emitter_defense_if_error_status_leaks():
    """Defense: even with error=True, free-to-paid-switch must not fuel-GIVEUP."""
    clock = FakeClock(time.time())
    e, _sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    giveups: list[tuple[str, str]] = []
    retries: list[str] = []
    e.failed_turn_retry_fn = lambda k: retries.append(k)
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    e.turn_ended(
        at=clock(),
        error=True,
        error_class="free-to-paid-switch",
        error_line="exit 1: Free usage limit reached. Subscribe to OpenCode Go",
    )
    assert not any(r == "out-of-fuel" for _, r in giveups), giveups
    # May retry as generic failed-turn if status=error leaked; must not clear as fuel.
    assert not any("out-of-fuel" in m for m in logs if "GIVEUP" in m), logs
    e.stop()


def test_fr8578_wrapper_pins_non_terminal_class_when_switch_paid(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        str(tmp_path / "opencode.exe"),
        tmp_path / "run",
        None,
    )
    ps1 = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "FR #8578" in ps1
    assert "free-to-paid-switch" in ps1
    assert "$script:ocSwitchPaid -and $hitLimit" in ps1
    # Terminal out-of-fuel still present for the failed-switch path.
    assert "if ($hitLimit) { $teClass = 'out-of-fuel' }" in ps1
    assert "Try-OpencodeSwitchToPaid" in ps1
    assert "Write-OpencodeTurnMarker 'turn_ended'" in ps1
