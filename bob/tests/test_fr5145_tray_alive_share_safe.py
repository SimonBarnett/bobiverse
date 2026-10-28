"""FR #5145: tray.alive writers must share-lock + retry (no exclusive Set-Content race).

MarchHare 2026-10-28: trayAliveTimer Set-Content raced bob-tray.exe File.WriteAllText →
RuntimeError 'being used by another process' → FR #5050 intake storm (fail-sig 54a2c007).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)

START = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
PS = shutil.which("powershell") or "powershell.exe"


def test_fr5145_write_bob_tray_alive_uses_fileshare_readwrite():
    t = START.read_text(encoding="utf-8")
    assert "FR #5145" in t
    fn = t[t.index("function Write-BobTrayAlive") : t.index("function Invoke-BobTrayStartWorkerQueue")]
    assert "FileShare" in fn
    assert "ReadWrite" in fn
    assert "Retries" in fn
    assert "[IO.File]::Open" in fn or "[System.IO.File]::Open" in fn
    assert "Set-Content -LiteralPath" not in fn


def test_fr5145_tray_alive_timer_uses_write_bob_tray_alive():
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #5145" in w
    i = w.index("$script:trayAliveSub = Register-ObjectEvent")
    chunk = w[i : i + 1800]
    assert "Write-BobTrayAlive" in chunk
    assert "Set-Content -LiteralPath (Join-Path $dir 'tray.alive')" not in chunk


def test_fr5145_bob_tray_cs_write_uses_fileshare():
    t = CS.read_text(encoding="utf-8-sig")
    assert "FR #5145" in t
    i = t.index("void WriteTrayAlive()")
    chunk = t[i : i + 1200]
    assert "FileShare.ReadWrite" in chunk
    assert "File.WriteAllText(aliveFile" not in chunk


@WIN
def test_fr5145_concurrent_write_bob_tray_alive_no_throw(tmp_path):
    """Two rapid writers must not throw; at least one stamp lands."""
    d = tmp_path / "startworker"
    d.mkdir()
    script = r"""
$ErrorActionPreference = 'Stop'
. '{start}'
$dir = '{dir}'
$jobs = 1..8 | ForEach-Object {{
  Start-Job -ScriptBlock {{
    param($s, $d)
    . $s
    1..20 | ForEach-Object {{ [void](Write-BobTrayAlive -Dir $d); Start-Sleep -Milliseconds 5 }}
  }} -ArgumentList '{start}', $dir
}}
$jobs | Wait-Job | Out-Null
$jobs | Receive-Job | Out-Null
$jobs | Remove-Job -Force
if (-not (Test-Path -LiteralPath (Join-Path $dir 'tray.alive'))) {{ throw 'missing tray.alive' }}
'OK'
""".format(start=str(START).replace("'", "''"), dir=str(d).replace("'", "''"))
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "OK" in r.stdout
    assert (d / "tray.alive").is_file()
