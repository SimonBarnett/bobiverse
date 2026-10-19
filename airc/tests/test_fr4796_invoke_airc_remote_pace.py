"""FR #4796: Invoke-AircRemote paces multi-line outbox bursts + post-burst cool."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

PS = Path(os.environ.get("AIRC_POWERSHELL") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
SCRIPT = ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1"
# Flat compose may also stage scripts/Invoke-AircRemote.ps1
if not SCRIPT.is_file():
    SCRIPT = ROOT / "scripts" / "Invoke-AircRemote.ps1"


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not PS.is_file() or not SCRIPT.is_file(),
    reason="FR #4796 requires Windows PowerShell + Invoke-AircRemote.ps1",
)


def _run(*extra: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    cmd = [
        str(PS),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def test_fr4796_selftest_mentions_pace():
    r = _run("-SelfTest")
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    blob = (r.stdout or "") + (r.stderr or "")
    assert "SELFTEST PASSED" in blob
    assert "FR #4796" in blob or "OutboxPaceMs" in blob


def test_fr4796_script_declares_pace_params():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "OutboxPaceMs" in text
    assert "PostBurstCoolMs" in text
    assert "BurstReplyThreshold" in text
    assert "FR #4796" in text


def test_fr4796_outbox_pace_delays_multi_line_put(tmp_path: Path):
    """Multi-line outbox write with PaceMs>0 must take wall time (driver pacing)."""
    local = tmp_path / "blob.bin"
    # Enough bytes for >1 IRC-safe PUT chunk at ChunkBytes=64
    local.write_bytes(b"A" * 200)
    outbox = tmp_path / "outbox.txt"
    sandbox = tmp_path / "drop"
    sandbox.mkdir(parents=True, exist_ok=True)
    remote = sandbox / "blob.bin"
    t0 = time.perf_counter()
    r = _run(
        "-MachineId",
        "tm",
        "-Action",
        "Put",
        "-LocalFile",
        str(local),
        "-Path",
        str(remote),
        "-SandboxRoot",
        str(sandbox),
        "-Outbox",
        str(outbox),
        "-OutboxPaceMs",
        "200",
        "-ChunkBytes",
        "64",
    )
    elapsed = time.perf_counter() - t0
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    lines = [ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 3, lines  # meta + chunks + end
    # (n-1) gaps * 200ms => at least ~400ms for 3+ lines
    assert elapsed >= 0.35, f"expected outbox pacing delay, elapsed={elapsed:.3f}s lines={len(lines)}"
