"""FR #7603: Invoke-BobTimed returns when the timeout fires.

A blocking Stop() on hung work keeps the caller stuck. BeginStop signals
cancel and returns. The hung block must hand control back within the
timeout plus 2 seconds. Generic fixture only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PEEK = ROOT / "tray" / "src" / "Private" / "Get-BobFleetPeek.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def test_fr7603_source_uses_beginstop_not_blocking_stop():
    text = PEEK.read_text(encoding="utf-8-sig")
    start = text.index("function Invoke-BobTimed")
    end = text.index("function ConvertTo-BobUncPath")
    body = text[start:end]
    assert "BeginStop" in body
    assert ".Stop()" not in body


@needs_ps
def test_fr7603_hung_block_returns_within_timeout_plus_2s():
    script = f"""
$ErrorActionPreference = 'Stop'
. '{PEEK}'
$sw = [Diagnostics.Stopwatch]::StartNew()
$r = Invoke-BobTimed -TimeoutMs 400 -Action {{
    [System.Threading.Thread]::Sleep(20000)
    'finished'
}}
$sw.Stop()
Write-Output ('ELAPSED=' + [int]$sw.ElapsedMilliseconds)
Write-Output ('TIMEDOUT=' + [bool]$r.timedOut)
Write-Output ('OK=' + [bool]$r.ok)
Write-Output ('ERR=' + [string]$r.error)
"""
    proc = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (proc.stdout or "") + "\n" + (proc.stderr or "")
    out = {}
    for ln in (proc.stdout or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v
    elapsed = int(out["ELAPSED"])
    assert out["TIMEDOUT"] == "True"
    assert out["OK"] == "False"
    assert out["ERR"] == "timeout"
    assert elapsed < 2400, elapsed
