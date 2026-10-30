"""FR #5196: fresh install and upgrade re-register the NSSM working directory."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"


@pytest.mark.parametrize("upgrade", [False, True], ids=["fresh-install", "upgrade"])
def test_registration_sets_appdirectory_on_install_and_upgrade(tmp_path, upgrade):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("PowerShell unavailable")
    script = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '__INSTALL__', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer parse failed' }
$body = @($ast.EndBlock.Statements |
    Where-Object { $_ -is [System.Management.Automation.Language.TryStatementAst] })[0].Body
# Select only unconditional service removal/registration statements, not branches.
$steps = @($body.Statements | Where-Object {
    $_.Extent.Text -match '^Remove-BobiverseService ' -or
    $_.Extent.Text -match "^\[void\]\(Invoke-BobiverseNssmChecked .*'install'," -or
    $_.Extent.Text -match "^\[void\]\(Invoke-BobiverseNssmChecked .*'AppDirectory',"
})
if ($steps.Count -ne 3) { throw 'Missing unconditional registration steps' }
$ServiceName = 'ircBob'
$InstallRoot = '__ROOT__'
$Nssm = 'nssm'
$script:registry = @{}
$script:hadPriorService = __UPGRADE__
if ($hadPriorService) { $script:registry.AppDirectory = 'obsolete-directory' }
function Remove-BobiverseService { param($Nssm, $Name)
    if ($Name -ne 'ircBob') { throw 'Wrong service removed' }
    $script:registry = @{}
}
function Invoke-BobiverseNssmChecked { param($Exe, $NssmArgs)
    if ($NssmArgs[1] -ne 'ircBob') { throw 'Wrong service registered' }
    if ($NssmArgs[0] -eq 'set') {
        $script:registry[$NssmArgs[2]] = $NssmArgs[3]
    }
}
foreach ($step in $steps) { & ([scriptblock]::Create($step.Extent.Text)) }
if ($script:registry.AppDirectory -ne (Join-Path $InstallRoot 'scripts')) {
    throw 'AppDirectory missing or incorrect after registration'
}
"""
    script = (
        script.replace("__INSTALL__", str(INSTALL).replace("'", "''"))
        .replace("__ROOT__", str(tmp_path / "bob install").replace("'", "''"))
        .replace("__UPGRADE__", "$true" if upgrade else "$false")
    )
    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
