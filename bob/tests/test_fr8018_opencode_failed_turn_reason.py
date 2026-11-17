"""FR #8018: OpenCode failed-turn GIVEUP carries exit code + redacted stderr."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter

KEY = "FR SimonBarnett/bobiverse#8018"


def test_fr8018_sanitize_keeps_exit_code_and_redacts_secrets():
    why = bw.sanitize_failed_turn_reason(
        "process-exit",
        "exit 7: tool failed ghp_" + ("A" * 30) + " boom",
    )
    assert "process-exit" in why
    assert "exit 7" in why
    assert "tool failed" in why
    assert "ghp_" not in why
    assert "AAAA" not in why


def test_fr8018_format_opencode_turn_error_includes_code_and_stderr():
    cls, line = bw.format_opencode_turn_error(
        7, stderr="last line with detail\n", stdout="", hit_limit=False
    )
    assert cls == "process-exit"
    assert line.startswith("exit 7:")
    assert "last line with detail" in line


def test_fr8018_format_opencode_turn_error_marks_fuel():
    cls, line = bw.format_opencode_turn_error(
        1,
        stderr="Error: 402 Payment Required\n",
        stdout="",
        hit_limit=True,
    )
    assert cls == "out-of-fuel"
    assert "exit 1" in line
    assert "402" in line or "Payment" in line


def test_fr8018_giveup_reason_includes_exit_and_stderr_snippet():
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    records: list[tuple[str, str]] = []
    e.session_log_write = lambda src, text: records.append((src, text))
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: None
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    secret = "ghp_" + ("A" * 30)
    err = dict(
        error=True,
        error_class="process-exit",
        error_line="exit 7: tool: failed to load runtime " + secret,
    )
    e.turn_ended(at=clock(), **err)
    e.turn_ended(at=clock(), **err)
    assert len(giveups) == 1
    assert giveups[0][0] == KEY
    reason = giveups[0][1]
    assert reason.startswith("failed-turn")
    assert "exit 7" in reason
    assert "failed to load runtime" in reason
    assert "ghp_" not in reason
    assert "AAAA" not in reason
    assert any(src == "failed-turn" for src, _ in records), records
    assert any(src == "giveup" for src, _ in records), records
    for src, text in records:
        assert "ghp_" not in text
        assert "AAAA" not in text
    e.stop()


def test_fr8018_launch_wrapper_redacts_snip_before_marker(tmp_path: Path):
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
    assert "<redacted>" in ps1
    assert "ghp_" in ps1 or "github_pat_" in ps1



def test_fr8018_fuel_text_giveup_is_out_of_fuel_not_failed_turn():
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    records: list[tuple[str, str]] = []
    e.session_log_write = lambda src, text: records.append((src, text))
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: None
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    e.turn_ended(
        at=clock(),
        error=True,
        error_class="out-of-fuel",
        error_line="exit 1: 402 Payment Required",
    )
    assert len(giveups) == 1
    assert giveups[0][1] == "out-of-fuel"
    assert not any("failed-turn" in r for _, r in giveups)
    assert any(src == "giveup" and "out-of-fuel" in text for src, text in records), records
    e.stop()


def test_fr8018_launch_wrapper_pins_stderr_on_turn_ended_marker(tmp_path: Path):
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
    assert "error_class" in ps1 or "ErrClass" in ps1
    assert "process-exit" in ps1
    assert "out-of-fuel" in ps1
    # Must not leave teErr as bare 'exit ' + code without stderr snippet path.
    assert "stderr" in ps1
    assert "Write-OpencodeTurnMarker 'turn_ended'" in ps1 or 'Write-OpencodeTurnMarker "turn_ended"' in ps1
