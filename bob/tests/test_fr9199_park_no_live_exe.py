# -*- coding: utf-8 -*-
"""FR #9199: intentional clickfalse/clicktrue park keeps Watch-only (no live bob-tray.exe drop)."""
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
START = BOB / "tray" / "tools" / "Start-BobFleetTray.ps1"
SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
INSTALL = BOB / "scripts" / "Install-BobTrayHotpatch.ps1"
ENSURE = BOB / "scripts" / "Ensure-BobTrayRunning.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9199_source_pins_helpers_and_call_sites():
    life = _txt(LIFE)
    assert "function Test-BobTrayIntentionalExeParkPresent" in life
    assert "function Remove-BobTrayLiveExeWhileParked" in life
    assert "clickfalse-park" in life
    assert "clicktrue-park" in life
    assert "FR #9199" in life
    # Restore must not revive live when intentional park is present.
    assert "Test-BobTrayIntentionalExeParkPresent" in life
    start = _txt(START)
    assert "Remove-BobTrayLiveExeWhileParked" in start or "Test-BobTrayIntentionalExeParkPresent" in start
    assert "FR #9199" in start
    sync = _txt(SYNC)
    assert "Remove-BobTrayLiveExeWhileParked" in sync or "IntentionalExePark" in sync
    assert "FR #9199" in sync
    install = _txt(INSTALL)
    assert "Remove-BobTrayLiveExeWhileParked" in install or "IntentionalExePark" in install
    assert "FR #9199" in install
    ensure = _txt(ENSURE)
    assert "IntentionalExePark" in ensure or "Remove-BobTrayLiveExeWhileParked" in ensure
    assert "FR #9199" in ensure


@needs_ps
def test_fr9199_remove_live_while_clickfalse_parked(tmp_path: Path):
    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    live = tools / "bob-tray.exe"
    park = tools / "bob-tray.exe.clickfalse-park"
    live.write_bytes(b"MZ-live")
    park.write_bytes(b"MZ-park")
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
$r = Remove-BobTrayLiveExeWhileParked -Root '{tmp_path}'
if (-not $r.Parked) {{ throw 'expected Parked' }}
if (-not $r.Removed) {{ throw 'expected Removed' }}
if ([IO.File]::Exists('{live}')) {{ throw 'live should be gone' }}
if (-not [IO.File]::Exists('{park}')) {{ throw 'park must remain' }}
$r2 = Remove-BobTrayLiveExeWhileParked -Root '{tmp_path}'
if (-not $r2.Parked) {{ throw 'still parked' }}
if ($r2.Removed) {{ throw 'second call should not remove' }}
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
def test_fr9199_restore_clickfix_skipped_when_clickfalse_present(tmp_path: Path):
    """FR #9044 restore must not create live beside intentional clickfalse park."""
    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    park_fix = tools / "bob-tray.exe.clickfix-park"
    park_false = tools / "bob-tray.exe.clickfalse-park"
    park_fix.write_bytes(b"MZ-fix")
    park_false.write_bytes(b"MZ-false")
    live = tools / "bob-tray.exe"
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
$got = Restore-BobTrayExeFromClickfixPark -Root '{tmp_path}'
if ($null -ne $got) {{ throw ('restore should return null, got ' + $got) }}
if ([IO.File]::Exists('{live}')) {{ throw 'live must not appear while clickfalse parked' }}
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
def test_fr9199_get_systray_exe_null_when_intentional_park(tmp_path: Path):
    tools = tmp_path / "tools"
    tools.mkdir(parents=True)
    (tools / "bob-tray.exe").write_bytes(b"MZ-live")
    (tools / "bob-tray.exe.clickfalse-park").write_bytes(b"MZ-park")
    # Minimal lifecycle + start helper extract via Start-BobFleetTray dots life
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
. '{START}'
# Start-BobFleetTray is a script with params; dotting may fail. Call helpers after defining from file.
""",
        encoding="utf-8",
    )
    # Parse Get-BobSystrayTrayExe from START by extracting function via life-only path:
    # After change, Get-BobSystrayTrayExe lives in Start-BobFleetTray.ps1 - invoke by loading function text.
    extract = tmp_path / "extract.ps1"
    extract.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{LIFE}'
$t = Get-Content -LiteralPath '{START}' -Raw
# Pull Get-BobSystrayTrayExe function body from file
$m = [regex]::Match($t, '(?s)function Get-BobSystrayTrayExe \{{.*?\\n\}}')
if (-not $m.Success) {{ throw 'Get-BobSystrayTrayExe not found' }}
Invoke-Expression $m.Value
$got = Get-BobSystrayTrayExe -Root '{tmp_path}'
if ($null -ne $got) {{ throw ('expected null, got ' + $got) }}
if ([IO.File]::Exists((Join-Path '{tmp_path}' 'tools\\bob-tray.exe'))) {{ throw 'live should be cleared' }}
Write-Output 'ok'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(extract)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "ok" in out