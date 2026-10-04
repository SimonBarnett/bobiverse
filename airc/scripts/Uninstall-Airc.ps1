#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1566: stop and remove the Airc Windows service (NSSM) during MSI /x uninstall.

.DESCRIPTION
  Called by the airc MSI deferred RunUninstall custom action (REMOVE="ALL" AND NOT
  UPGRADINGPRODUCTCODE) before RemoveFiles so scripts are still on disk.

  Stops and deletes SCM service "Airc" via Remove-BobiverseService.
  Does NOT delete ConsoleHome, console.password, operators.txt, or other secrets -
  those survive so a later reinstall can reclaim {machine}_console (FR #1552).
  Does NOT delete the install tree; MSI RemoveFiles owns that.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = '',
    [string]$ServiceName = 'Airc'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Flat stage (MSI) or split repo checkout
$common = Join-Path $here 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $common)) {
    $repoCommon = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) 'common\scripts\Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath $repoCommon) { $common = $repoCommon }
}
. $common

Write-Host 'INFO FR #1566: Uninstall-Airc - stop/remove service; keep ConsoleHome secrets'

if (-not (Test-BobiverseIsAdmin)) {
    # MSI deferred CA runs elevated; manual runs may need UAC.
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

if (-not $InstallRoot) {
    try { $InstallRoot = Join-Path (Get-BobiverseAiRoot) 'airc' } catch { $InstallRoot = '' }
}

# Prefer live AppParameters ConsoleHome for the log line only (never delete it).
$keptHome = ''
try {
    $ap = Get-BobiverseServiceAppParameters -ServiceName $ServiceName
    if ($ap) {
        $id = Get-BobiverseAircIdentityFromAppParameters -AppParameters $ap
        if ($id -and $id.ConsoleHome) { $keptHome = [string]$id.ConsoleHome }
    }
} catch { }

if (-not $keptHome -and $InstallRoot) {
    $snapPath = Join-Path $InstallRoot 'config\airc-install.json'
    if (Test-Path -LiteralPath $snapPath) {
        try {
            $snap = Get-Content -LiteralPath $snapPath -Raw -Encoding utf8 | ConvertFrom-Json
            if ($snap.ConsoleHome) { $keptHome = [string]$snap.ConsoleHome }
        } catch { }
    }
}

if ($keptHome) {
    Write-Host "INFO keeping ConsoleHome (secrets stay): $keptHome"
} else {
    Write-Host 'INFO ConsoleHome path unknown; still will not delete any profile home'
}

$nssmExe = Resolve-BobiverseNssm -Preferred $Nssm -ScriptDir $here
if (-not $nssmExe -or -not (Test-Path -LiteralPath $nssmExe)) {
    Write-Host 'WARN nssm.exe not found; trying sc.exe delete fallback for service only'
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        try { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue } catch { }
        $null = & sc.exe delete $ServiceName 2>&1
        Write-Host "INFO sc delete $ServiceName attempted"
    } else {
        Write-Host "INFO service $ServiceName absent"
    }
    Write-Host 'INFO FR #1566: Uninstall-Airc done (no ConsoleHome delete)'
    exit 0
}

try {
    Remove-BobiverseService -Nssm $nssmExe -Name $ServiceName
} catch {
    # Return=ignore on the MSI CA; still exit 0 so ARP cleanup continues.
    Write-Host ("WARN Remove-BobiverseService: {0}" -f $_.Exception.Message)
}

Write-Host 'INFO FR #1566: Uninstall-Airc done (ConsoleHome secrets kept; tree is MSI RemoveFiles)'
exit 0
