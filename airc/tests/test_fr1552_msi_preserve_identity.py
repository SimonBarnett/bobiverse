"""FR #1552: MSI upgrade/reinstall preserves Airc AppParameters identity (ConsoleHome etc.)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "scripts" / "Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "scripts" / "Install-AircConsole.ps1"
OPS = ROOT / "docs" / "airc-ops.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_common_helpers_parse_airc_appparameters_static():
    t = _txt(COMMON)
    assert "function Get-BobiverseServiceAppParameters" in t
    assert "function Get-BobiverseAppParam" in t
    assert "function Get-BobiverseAircIdentityFromAppParameters" in t


def test_install_airc_reads_existing_appparameters_before_defaults():
    t = _txt(INSTALL)
    assert "Get-BobiverseServiceAppParameters" in t
    assert "Get-BobiverseAircIdentityFromAppParameters" in t
    assert t.index("Get-BobiverseServiceAppParameters") < t.index("LocalSystem using existing Admin ConsoleHome")
    assert "preserving ConsoleHome from service AppParameters" in t
    assert "airc-install.json" in t
    assert "FR #1552" in t


def test_install_aircconsole_captures_before_teardown():
    t = _txt(INSTALL_CONSOLE)
    assert "Get-BobiverseServiceAppParameters" in t
    # Capture must happen before Remove-AircConsoleService tear-down.
    assert t.index("preserving identity from existing") < t.index("Remove-AircConsoleService")
    assert "priorId.OperatorsFile" in t or "OperatorsFile" in t


def test_ops_doc_upgrade_preserves_identity():
    t = _txt(OPS)
    assert "FR #1552" in t
    assert "AppParameters" in t
    assert "SASL 904" in t or "NickServ" in t


@win
def test_parse_appparameters_identity_roundtrip(tmp_path: Path):
    script = tmp_path / "parse.ps1"
    sample = (
        r'-NoProfile -ExecutionPolicy Bypass -File "C:\ai\airc\scripts\Start-AircConsole-Fleet.ps1" '
        r'-ServiceMode -ConsoleHome "C:\Users\Default\.airc" '
        r'-PasswordFile "C:\Users\Default\.airc\console.password" '
        r'-OperatorsFile "C:\Users\Default\.airc\operators.txt" '
        r'-MachineId "win-mpre8vi4u6u"'
    )
    body = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
$raw = @'
{sample}
'@
$id = Get-BobiverseAircIdentityFromAppParameters -AppParameters $raw
'ch=' + $id.ConsoleHome
'mid=' + $id.MachineId
'pf=' + $id.PasswordFile
'of=' + $id.OperatorsFile
'ln=' + $id.Launcher
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert "ch=C:\\Users\\Default\\.airc" in lines
    assert "mid=win-mpre8vi4u6u" in lines
    assert "pf=C:\\Users\\Default\\.airc\\console.password" in lines
    assert "of=C:\\Users\\Default\\.airc\\operators.txt" in lines
    assert any(ln.startswith("ln=") and "Start-AircConsole-Fleet.ps1" in ln for ln in lines)


@win
def test_empty_appparameters_yields_empty_identity(tmp_path: Path):
    script = tmp_path / "empty.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
$id = Get-BobiverseAircIdentityFromAppParameters -AppParameters ''
if ($id.ConsoleHome -or $id.MachineId -or $id.Launcher) {{ throw 'expected empty' }}
'ok'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
