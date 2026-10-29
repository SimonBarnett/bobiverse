"""FR #5196: MSI install and upgrade must restore the NSSM working directory."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "bob" / "scripts" / "Install-Bob.ps1"


def test_msi_runs_installer_on_upgrade_as_well_as_fresh_install():
    pack = (ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert '<Custom Action="RunInstall" After="RollbackRecover">NOT REMOVE~="ALL"</Custom>' in pack
    installer = INSTALLER.read_text(encoding="utf-8-sig")
    register = installer.index("@('install', $ServiceName, 'powershell.exe')")
    working_dir = installer.index("@('set', $ServiceName, 'AppDirectory'")
    start = installer.index("Start-Service $ServiceName")
    assert register < working_dir < start
    # No fresh-install-only gate around service registration / configuration.
    block = installer[installer.rfind("\n", 0, register) + 1:
                      installer.index("\n", working_dir)]
    assert not re.search(r"(?m)^\s*(if|else|switch)\b", block)


def test_installer_sets_appdirectory_to_installed_scripts(tmp_path):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("PowerShell unavailable")
    installer = INSTALLER.read_text(encoding="utf-8-sig")
    statement = next(
        line for line in installer.splitlines()
        if "@('set', $ServiceName, 'AppDirectory'" in line
    )
    install_root = tmp_path / "install with spaces" / "bob"
    script = """
$ErrorActionPreference = 'Stop'
$InstallRoot = $args[0]
$ServiceName = 'ircBob'
$Nssm = 'mock-nssm'
function Invoke-BobiverseNssmChecked {
    param($Exe, $NssmArgs)
    if ($Exe -ne 'mock-nssm') { throw 'Unexpected NSSM executable' }
    if ($NssmArgs.Count -ne 4 -or $NssmArgs[0] -ne 'set' -or
        $NssmArgs[1] -ne 'ircBob' -or $NssmArgs[2] -ne 'AppDirectory' -or
        $NssmArgs[3] -ne (Join-Path $InstallRoot 'scripts')) {
        throw 'Incorrect service working directory'
    }
    $script:configured = $true
}
""" + statement + """
if (-not $script:configured) { throw 'AppDirectory was not set' }
"""
    probe = tmp_path / "check-appdirectory.ps1"
    probe.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(probe), str(install_root)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
