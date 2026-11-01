#Requires -Version 4.0
<#
.SYNOPSIS
  FR #5737: deploy Sysinternals PsExec at airc install/UPDATE (pinned SHA-256).

.DESCRIPTION
  Sysinternals license forbids redistributing PsExec inside the MSI. This script
  downloads the official PSTools.zip (pinned hash), caches it under
  %ProgramData%\bobiverse\tools\cache\, and extracts PsExec.exe to
  %ProgramData%\bobiverse\tools\PsExec.exe. LEGION never downloads at verb time;
  it only verifies / redeploys from that local cache.

  EULA is accepted non-interactively later via PsExec -accepteula on the run line.
#>
[CmdletBinding()]
param(
    [string]$Python = '',
    [string]$AirCPsexecPath = '',
    [switch]$OfflineOnly
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-DeployPython {
    param([string]$Hint)
    if ($Hint -and (Test-Path -LiteralPath $Hint)) { return $Hint }
    foreach ($c in @(
            (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
            (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
            'C:\Python\Python312\python.exe',
            'C:\Python312\python.exe'
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return ''
}

$py = Resolve-DeployPython -Hint $Python
if (-not $py) {
    Write-Host 'WARN FR #5737 Deploy-AircPsExec: python not found; skip PsExec deploy'
    exit 0
}

$env:PYTHONPATH = $here
if ($AirCPsexecPath) { $env:AIRC_PSEXEC_PATH = $AirCPsexecPath }

$code = @'
import json, os, sys
from airc_network_installer.psexec_deploy import deploy_psexec, psexec_dest, cache_zip_path

offline = (os.environ.get("AIRC_PSEXEC_OFFLINE") or "").strip() in ("1", "true", "yes")
hit = deploy_psexec(allow_network=not offline)
print(json.dumps(hit))
sys.exit(0 if hit.get("ok") else 2)
'@

if ($OfflineOnly) { $env:AIRC_PSEXEC_OFFLINE = '1' }

$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$out = & $py -c $code 2>&1
$ErrorActionPreference = $prev
$codeExit = $LASTEXITCODE
$line = ($out | Out-String).Trim()
Write-Host ("INFO FR #5737 Deploy-AircPsExec: {0}" -f $line)
if ($codeExit -ne 0) {
    Write-Host ("WARN FR #5737 Deploy-AircPsExec failed exit={0}" -f $codeExit)
    exit $codeExit
}

# ACL: SYSTEM + Administrators on tools dir (best effort).
try {
    $dest = if ($AirCPsexecPath) { $AirCPsexecPath } else { Join-Path $env:ProgramData 'bobiverse\tools\PsExec.exe' }
    $tools = Split-Path -Parent $dest
    if (Test-Path -LiteralPath $tools) {
        icacls $tools /inheritance:r | Out-Null
        icacls $tools /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null
        Write-Host ("INFO FR #5737 ACL SYSTEM+Administrators on {0}" -f $tools)
    }
} catch {
    Write-Host ("WARN FR #5737 ACL: {0}" -f $_.Exception.Message)
}
exit 0
