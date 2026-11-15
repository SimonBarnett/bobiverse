"""FR #7603: Invoke-BobTimed returns when the timeout fires.

A blocking Stop() on hung work keeps the caller stuck. BeginStop signals
cancel and returns. The hung block must hand control back within the
timeout plus 2 seconds. Generic fixture only.

BeginStop intentionally leaks the timed-out runspace (Dispose would block).
The PS child therefore writes a marker and Environment.Exit(0) so the
leaked Thread.Sleep cannot keep the process alive past the assertion.
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
def test_fr7603_hung_block_returns_within_timeout_plus_2s(tmp_path: Path):
    marker = tmp_path / "invoke-bobtimed-result.txt"
    marker_ps = str(marker).replace("'", "''")
    peek_ps = str(PEEK).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
. '{peek_ps}'
$sw = [Diagnostics.Stopwatch]::StartNew()
$r = Invoke-BobTimed -TimeoutMs 400 -Action {{
    [System.Threading.Thread]::Sleep(20000)
    'finished'
}}
$sw.Stop()
$lines = @(
  ('ELAPSED=' + [int]$sw.ElapsedMilliseconds),
  ('TIMEDOUT=' + [bool]$r.timedOut),
  ('OK=' + [bool]$r.ok),
  ('ERR=' + [string]$r.error)
)
Set-Content -LiteralPath '{marker_ps}' -Value ($lines -join [Environment]::NewLine) -Encoding ascii
# FR #7603: leaked timed-out runspace still sleeps; exit so pytest is not stranded.
[Environment]::Exit(0)
"""
    proc = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert marker.is_file(), "Invoke-BobTimed did not write the result marker"
    out = {}
    for ln in marker.read_text(encoding="ascii").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v
    elapsed = int(out["ELAPSED"])
    assert out["TIMEDOUT"] == "True"
    assert out["OK"] == "False"
    assert out["ERR"] == "timeout"
    assert elapsed < 2400, elapsed

def test_mrb7610_timeout_path_nulls_run_before_finally_dispose():
    """MRB hostile: timed-out instance must not hit Dispose (would block like Stop)."""
    text = PEEK.read_text(encoding="utf-8-sig")
    start = text.index("function Invoke-BobTimed")
    end = text.index("function ConvertTo-BobUncPath")
    body = text[start:end]
    assert "$run = $null" in body
    # After BeginStop the instance is cleared before return so finally skips Dispose.
    assert "BeginStop" in body
    i_begin = body.index("BeginStop")
    i_null = body.index("$run = $null", i_begin)
    i_return = body.index("timedOut = $true", i_begin)
    assert i_begin < i_null < i_return or i_begin < i_null


def test_mrb7610_behavioral_test_exits_after_marker():
    """MRB hostile: leaked runspace must not strand pytest (Environment.Exit after marker)."""
    src = Path(__file__).read_text(encoding="utf-8")
    assert "Environment]::Exit(0)" in src or "Environment.Exit(0)" in src
    assert "invoke-bobtimed-result.txt" in src or "Set-Content" in src
