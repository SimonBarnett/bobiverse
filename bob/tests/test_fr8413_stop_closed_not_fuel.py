"""FR #8413: job-ended stop closed is not a fuel GIVEUP."""
from __future__ import annotations

import bob.scripts.bob_worker as bw
import bob.scripts.opencode_turn_guard as g


def test_fr8413_done_or_nack_is_finished_even_if_closed():
    job = "FR SimonBarnett/bobiverse#8333"
    done = f"PRIVMSG #redqueen :DONE {job} https://github.com/SimonBarnett/bobiverse/pull/1\n"
    assert g.opencode_turn_stop_reason("CLOSED", done, job) == "finished"
    nack = f"NACK {job} busy\n"
    assert g.opencode_turn_stop_reason("OPEN", nack, job) == "finished"
    assert g.opencode_turn_stop_reason("CLOSED", "", job) == "closed"
    assert g.opencode_turn_stop_reason("OPEN", f"ACK {job}\n", job) == ""


def test_fr8413_wrapper_stop_closed_skips_fuel_log(tmp_path):
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    script = next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))
    assert "process-exit:stop-closed" in script
    assert "stop finished" in script
    assert "already-finished" in script
    assert "$script:ocSkipFuelLog = $true" in script
    assert "if (-not $script:ocSkipFuelLog)" in script
    # Other stop reasons still hand back as job-ended.
    assert "job-ended" in script


def test_fr8509_already_finished_also_skips_fuel_log(tmp_path):
    """FR #8509: stop finished must set ocSkipFuelLog like stop closed."""
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    script = next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))
    i_fin = script.index("if ($stopLine -eq 'stop finished')")
    i_cls = script.index("if ($stopLine -eq 'stop closed')")
    assert i_fin < i_cls
    finished_block = script[i_fin:i_cls]
    assert "$script:ocSkipFuelLog = $true" in finished_block
    assert "already-finished" in finished_block
    closed_block = script[i_cls : i_cls + 500]
    assert "$script:ocSkipFuelLog = $true" in closed_block
