"""FR #3909: BobiverseTrayWatchdog must not flash a blank PowerShell console.

-WindowStyle Hidden only hides after powershell.exe creates a console. On an
interactive LogonType task that repeats every minute, the blank window steals
focus. Fix: launch via conhost.exe --headless (Win10 21H2+ / Server 2022),
lighten the tray-present probe, and default the interval to 5 minutes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INTERACTIVE = ROOT / "bob" / "scripts" / "Start-BobTrayInteractive.ps1"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobTrayRunning.ps1"
TROUBLE = (
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
)
BOB_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr3909_common_has_headless_powershell_helper():
    t = _read(COMMON)
    assert "function Get-BobiverseHeadlessPowerShellLaunch" in t
    assert "conhost.exe" in t
    assert "--headless" in t
    assert "FR #3909" in t
    assert "19044" in t  # Win10 21H2 / Server 2022 gate


def test_fr3909_interactive_registers_conhost_for_tray_and_watchdog():
    t = _read(INTERACTIVE)
    assert "FR #3909" in t
    assert "Get-BobiverseHeadlessPowerShellLaunch" in t
    assert "conhost" in t.lower()
    # Both BobiverseTray and BobiverseTrayWatchdog use the helper.
    assert t.count("Get-BobiverseHeadlessPowerShellLaunch") >= 2
    # Default interval is 5 minutes (was 1; blank console every minute).
    assert "WatchdogMinutes = 5" in t or "WatchdogMinutes=5" in t
    # Must not register bare powershell.exe as Execute for the watchdog when helper is used.
    # The New-ScheduledTaskAction for watchdog must use the helper's Execute.
    i_wd = t.find("$WatchdogTaskName")
    assert i_wd > 0
    assert "New-ScheduledTaskAction -Execute $wdLaunch.Execute" in t or (
        "New-ScheduledTaskAction -Execute $launch.Execute" in t
    )


def test_fr3909_ensure_prefers_fast_get_process():
    t = _read(ENSURE)
    assert "FR #3909" in t
    # Fast path before Win32_Process CIM (which can take ~1 min on a busy box).
    assert "Get-Process" in t
    assert "bob-tray" in t
    i_gp = t.find("Get-Process")
    i_cim = t.find("Get-CimInstance Win32_Process")
    assert i_gp > 0
    if i_cim > 0:
        assert i_gp < i_cim


def test_fr3909_docs_or_skill_mention_headless():
    found = False
    for p in (TROUBLE, BOB_SKILL):
        if p.is_file() and ("FR #3909" in p.read_text(encoding="utf-8") or "conhost" in p.read_text(encoding="utf-8").lower()):
            found = True
            break
    assert found, "troubleshooting or bob skill must mention FR #3909 / conhost"


@win
def test_fr3909_helper_returns_conhost_on_server2022():
    ps = r"""
$ErrorActionPreference = 'Stop'
. $env:FR3909_COMMON
$r = Get-BobiverseHeadlessPowerShellLaunch -PowerShellArguments '-NoProfile -WindowStyle Hidden -Command "exit 0"'
if (-not $r) { Write-Output 'FAIL null'; exit 2 }
Write-Output ("OK mode={0} execute={1}" -f $r.Mode, $r.Execute)
if ($r.Mode -eq 'conhost-headless') {
  if ($r.Argument -notmatch '--headless') { Write-Output 'FAIL no-headless-arg'; exit 3 }
  if ($r.Execute -notmatch 'conhost\.exe$') { Write-Output 'FAIL not-conhost'; exit 4 }
}
exit 0
"""
    env = dict(os.environ)
    env["FR3909_COMMON"] = str(COMMON)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK mode=" in out, out
    # This seat is Server 2022 — expect conhost-headless.
    build = int(
        subprocess.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').CurrentBuildNumber",
            ],
            text=True,
        ).strip()
        or "0"
    )
    if build >= 19044:
        assert "mode=conhost-headless" in out, out


@win
def test_fr3909_interactive_parses():
    ps = r"""
$ErrorActionPreference = 'Stop'
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($env:FR3909_INTERACTIVE, [ref]$null, [ref]$errs)
if ($errs -and $errs.Count -gt 0) { $errs | ForEach-Object { Write-Output $_.ToString() }; exit 2 }
Write-Output 'PARSE_OK'
exit 0
"""
    env = dict(os.environ)
    env["FR3909_INTERACTIVE"] = str(INTERACTIVE)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "PARSE_OK" in out
