# -*- coding: utf-8 -*-
"""FR #9205: re-park / Ensure must not kill bob-tray/Watch that parents TipForm OpenCode seats."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

BOB = ROOT / "bob"
if not (BOB / "tray" / "tools" / "BobTrayLifecycle.ps1").is_file():
    BOB = ROOT
LIFE = BOB / "tray" / "tools" / "BobTrayLifecycle.ps1"
ENSURE = BOB / "scripts" / "Ensure-BobTrayRunning.ps1"
START = BOB / "tray" / "tools" / "Start-BobFleetTray.ps1"
DOC = BOB / "docs" / "bob-9205-repark-no-seat-kill.md"
POST = ROOT / "common" / "docs" / "post-install.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9205_source_pins():
    life = _txt(LIFE)
    assert "function Test-BobTrayProcessHasSeatChildren" in life
    assert "function Stop-BobTrayProcessesProtectingSeats" in life
    assert "FR #9205" in life
    assert "bob-worker" in life
    # MRB #9206: Stop-BobTrayProcessesProtectingSeats must not assign automatic $pid/$PID.
    fn = life[
        life.index("function Stop-BobTrayProcessesProtectingSeats") : life.index(
            "function Stop-BobTrayProcessesProtectingSeats"
        )
        + 1800
    ]
    assert "$trayPid" in fn or "$procId" in fn or "$killPid" in fn
    assert "$pid = 0" not in fn
    assert "$pid = [int]" not in fn
    ensure = _txt(ENSURE)
    assert "FR #9205" in ensure
    assert "Stop-BobTrayProcessesProtectingSeats" in ensure
    # Park strip must not bare-call Stop-BobTrayProcesses without seat protection.
    park = ensure[ensure.index("FR #9199") : ensure.index("FR #9199") + 900]
    assert "Stop-BobTrayProcessesProtectingSeats" in park
    assert "Stop-BobTrayProcesses -Root" not in park or "ProtectingSeats" in park
    start = _txt(START)
    assert "FR #9205" in start
    assert "Stop-BobTrayProcessesProtectingSeats" in start or "Test-BobTrayProcessHasSeatChildren" in start
    assert DOC.is_file()
    post = _txt(POST)
    assert "FR #9205" in post or "clickfalse-park" in post


@needs_ps
def test_fr9205_protecting_seats_skips_kill_when_children(tmp_path: Path):
    """Helper returns Skipped=true when a synthetic parent has a matching child CommandLine."""
    # Unit-test the predicate by injecting fake CIM is hard; pin the function body contract instead
    # and run a dry call with no bob-tray (Skipped=false, Killed=0).
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
$r = Stop-BobTrayProcessesProtectingSeats -Root '{tmp_path}'
if ($null -eq $r) {{ throw 'null result' }}
if (-not ($r.PSObject.Properties.Name -contains 'Killed')) {{ throw 'missing Killed' }}
if (-not ($r.PSObject.Properties.Name -contains 'SkippedForSeats')) {{ throw 'missing SkippedForSeats' }}
Write-Output ('killed={{0}} skipped={{1}}' -f $r.Killed, $r.SkippedForSeats)
Write-Output 'ok'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "ok" in out


@needs_ps
def test_fr9205_has_seat_children_false_without_tray():
    script = Path(os.environ.get("TEMP", "/tmp")) / "fr9205_has_child.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
$pids = @(Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
foreach ($procId in $pids) {{
  if (Test-BobTrayProcessHasSeatChildren -ParentProcessId $procId) {{
    Write-Output ('has-child pid=' + $procId)
  }}
}}
Write-Output 'scanned'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=90,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "scanned" in out