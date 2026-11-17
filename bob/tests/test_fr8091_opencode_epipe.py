"""FR #8091: OpenCode EPIPE — keep draining pipes; rich GIVEUP; one retry."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter

KEY = "MRB SimonBarnett/bobiverse#8091"


def test_fr8091_drain_chatty_child_no_epipe():
    """Child writes a lot on both streams after a slow start; drain finishes cleanly."""
    child = (
        "import sys, time\n"
        "time.sleep(0.35)\n"
        "for i in range(400):\n"
        "    sys.stdout.write('OUT-%04d-' % i + ('x' * 64) + '\\n')\n"
        "    sys.stderr.write('ERR-%04d-' % i + ('y' * 64) + '\\n')\n"
        "    if i % 40 == 0:\n"
        "        sys.stdout.flush(); sys.stderr.flush()\n"
        "sys.stdout.flush(); sys.stderr.flush()\n"
    )
    code, out, err = bw.run_with_drained_pipes(
        [sys.executable, "-c", child], timeout=30.0
    )
    assert code == 0, (code, out[-200:], err[-200:])
    assert "OUT-0000-" in out and "OUT-0399-" in out
    assert "ERR-0000-" in err and "ERR-0399-" in err


def test_fr8091_callback_error_does_not_stop_drain():
    """A raising on_line callback must not close the pipe before EOF."""
    import subprocess

    lines = []

    def boom(text: str) -> None:
        lines.append(text)
        if len(lines) == 2:
            raise RuntimeError("session_log blew up")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time\n"
            "for i in range(50):\n"
            "    sys.stderr.write('line-%d\\n' % i); sys.stderr.flush()\n"
            "    time.sleep(0.01)\n",
        ],
        stderr=subprocess.PIPE,
    )
    ring, thread = bw.start_agent_stderr_capture(proc.stderr, on_line=boom)
    assert proc.wait(timeout=20) == 0
    thread.join(timeout=5)
    assert len(lines) >= 40, len(lines)
    assert any("line-49" in ln for ln in lines) or "line-49" in ring.tail_text()


def test_fr8091_format_includes_exit_tail_and_log_name():
    stderr = "\n".join("noise-%d" % i for i in range(25))
    stderr += "\nEPIPE: broken pipe, write\n"
    cls, line = bw.format_opencode_turn_error(
        1,
        stderr=stderr,
        stdout="",
        hit_limit=False,
        log_name=r"C:\logs\SimonBarnett-bobiverse-MRB-8091-redqueen-1-20261117T164200Z.log",
    )
    assert cls == "epipe"
    assert line.startswith("exit 1:")
    assert "EPIPE" in line
    assert "noise-24" in line or "noise-20" in line
    assert "noise-0" not in line  # only last ~20
    assert "log=SimonBarnett-bobiverse-MRB-8091-redqueen-1-20261117T164200Z.log" in line
    assert bw.is_epipe_turn_error(cls, line)


def test_fr8091_giveup_reason_has_exit_and_stderr_tail():
    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: None
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.on_outbox("ACK " + KEY)
    err = dict(
        error=True,
        error_class="epipe",
        error_line=(
            "exit 1: tip line | EPIPE: broken pipe, write "
            "log=SimonBarnett-bobiverse-MRB-8089-redqueen-11676-20261117T164000Z.log"
        ),
    )
    e.turn_ended(at=clock(), **err)  # retry once
    e.turn_ended(at=clock(), **err)  # GIVEUP
    assert len(giveups) == 1
    reason = giveups[0][1]
    assert reason.startswith("failed-turn")
    assert "epipe" in reason
    assert "exit 1" in reason
    assert "EPIPE" in reason
    assert "log=SimonBarnett-bobiverse-MRB-8089-redqueen-11676-20261117T164000Z.log" in reason
    e.stop()


def test_fr8091_launch_wrapper_keeps_drain_and_epipe_retry(tmp_path: Path):
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
    assert "$script:ocEpipeTries = 0" in ps1
    assert "opencode-epipe: retry" in ps1
    assert "$capDir = Split-Path -Parent $turnsLog" in ps1
    assert "bob-oc-out-" in ps1
    assert "elseif ($snip -match 'EPIPE|broken pipe'" in ps1 or "EPIPE|broken pipe" in ps1
    assert "$snipLines.Count -gt 20" in ps1
    assert "if ($proc -and $proc.HasExited)" in ps1
    assert "WaitForExit(5000)" in ps1
    # Watch loop must swallow tee/CIM errors so the child pipe stays open.
    assert "while (-not $proc.HasExited)" in ps1
    idx_while = ps1.index("while (-not $proc.HasExited)")
    idx_sleep = ps1.index("Start-Sleep -Milliseconds 100", idx_while)
    chunk = ps1[idx_while:idx_sleep]
    assert "try {" in chunk
