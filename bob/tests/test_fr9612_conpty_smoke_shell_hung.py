# -*- coding: utf-8 -*-
"""FR #9612: ConPTY smoke after recycle + empty call-*.log shell-hung detect."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw


def test_fr9612_probe_create_pseudoconsole_smoke_runs():
    logs = []
    out = bw.probe_create_pseudoconsole_hresult(log=logs.append)
    assert "ok" in out
    if out.get("skipped"):
        assert out.get("reason") in ("non-windows", "api-missing")
        return
    # On Windows with ConPTY, expect a logged HRESULT line.
    assert any("conpty-smoke:" in x and "FR #9612" in x for x in logs)
    assert "hresult" in out or "hresult_hex" in out


def test_fr9612_empty_call_logs_with_shell_tool_is_hung(tmp_path: Path):
    terminal = tmp_path / "terminal"
    terminal.mkdir()
    empty = terminal / "call-dead-0.log"
    empty.write_text("", encoding="utf-8")
    # Age the empty file
    old = time.time() - 40
    import os

    os.utime(empty, (old, old))
    (tmp_path / "events.jsonl").write_text(
        '{"type":"tool_started","name":"run_terminal_command"}\n',
        encoding="utf-8",
    )
    detail = bw.detect_grok_empty_terminal_calls(tmp_path, min_age_s=25.0, now=time.time)
    assert detail is not None
    assert detail["count"] >= 1
    assert "call-dead-0.log" in detail["empty_calls"]


def test_fr9612_empty_call_without_shell_tool_is_not_hung(tmp_path: Path):
    terminal = tmp_path / "terminal"
    terminal.mkdir()
    empty = terminal / "call-idle-0.log"
    empty.write_text("", encoding="utf-8")
    old = time.time() - 40
    import os

    os.utime(empty, (old, old))
    (tmp_path / "events.jsonl").write_text(
        '{"type":"tool_started","name":"read_file"}\n',
        encoding="utf-8",
    )
    assert bw.detect_grok_empty_terminal_calls(tmp_path, min_age_s=25.0) is None


def test_fr9612_fresh_empty_call_not_hung_yet(tmp_path: Path):
    terminal = tmp_path / "terminal"
    terminal.mkdir()
    (terminal / "call-fresh-0.log").write_text("", encoding="utf-8")
    (tmp_path / "events.jsonl").write_text(
        '{"type":"tool_started","name":"run_terminal_command"}\n',
        encoding="utf-8",
    )
    assert bw.detect_grok_empty_terminal_calls(tmp_path, min_age_s=25.0) is None


def test_fr9612_restart_agent_wires_conpty_smoke_source_pin():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "probe_create_pseudoconsole_hresult" in src
    assert "shell-hung-conpty" in src
    assert "detect_grok_empty_terminal_calls" in src
    assert "_check_grok_shell_hung" in src
    assert "FR #9612" in src
