"""FR #7976: the hard ceiling is stall time, not wall-clock age of a live turn."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _launch(tmp_path: Path) -> str:
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    return next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))


def test_fr7976_ceiling_uses_stall_not_wall_clock(tmp_path: Path):
    text = _launch(tmp_path)
    assert "$lastProgress = $runStarted" in text
    assert "if ($stallMs -ge $hardCeilingMs)" in text
    assert "if ($runMs -ge $hardCeilingMs)" not in text
    assert "--elapsed-ms ([int]$stallMs)" in text
    desc = [ln for ln in text.splitlines() if "$desc.Count -gt 0" in ln]
    assert desc and all("$lastProgress" not in ln for ln in desc)
    assert any("$cpuSum -gt $lastCpu" in ln and "$lastProgress" in ln for ln in text.splitlines())
    assert any("$len -gt $lastLen" in ln and "$lastProgress" in ln for ln in text.splitlines())
    assert any("$stamp -gt $lastWtStamp" in ln and "$lastProgress" in ln for ln in text.splitlines())
