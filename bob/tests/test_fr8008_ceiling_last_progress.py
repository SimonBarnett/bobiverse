"""FR #8008: hard-ceiling kill names last progress; CPU alone is not progress."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _launch(tmp_path: Path) -> str:
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    return next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))


def test_fr8008_kill_reason_names_last_progress(tmp_path: Path):
    text = _launch(tmp_path)
    assert "$lastProgress = $runStarted" in text
    assert "last progress" in text
    assert "$lastProgress.ToString" in text or "ToUniversalTime" in text or "o)" in text
    # stall clock still drives the ceiling
    assert "if ($stallMs -ge $hardCeilingMs)" in text
    assert "--elapsed-ms ([int]$stallMs)" in text


def test_fr8008_cpu_alone_does_not_reset_last_progress(tmp_path: Path):
    """CPU / descendant keep the short watchdog alive; hard-ceiling progress is output/worktree."""
    text = _launch(tmp_path)
    lines = text.splitlines()
    cpu_lines = [ln for ln in lines if "$cpuSum -gt $lastCpu" in ln]
    assert cpu_lines, "expected CPU busy check"
    assert all("$lastProgress" not in ln for ln in cpu_lines)
    assert any("$lastBeat" in ln for ln in cpu_lines)
    # output growth and worktree mtime still reset lastProgress
    assert any("$len -gt $lastLen" in ln and "$lastProgress" in ln for ln in lines)
    assert any("$stamp -gt $lastWtStamp" in ln and "$lastProgress" in ln for ln in lines)
