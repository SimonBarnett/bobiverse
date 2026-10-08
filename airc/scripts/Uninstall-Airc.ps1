#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1566 / #3292: stop and remove the Airc Windows service; optional full purge.

.DESCRIPTION
  Called by the airc MSI deferred RunUninstall custom action (REMOVE="ALL" AND NOT
  UPGRADINGPRODUCTCODE) before RemoveFiles so scripts are still on disk.

  Always stops and deletes SCM service "Airc" via Remove-BobiverseService.

  Fleet default (FR #1566 / #1599): does NOT delete ConsoleHome / secrets so a later
  reinstall can reclaim {machine}_console. MSI RemoveFiles owns the heat-laid tree.

  FR #3292 purge (AIRC_PURGE=1, -Purge, or workstation install manifest purge_default):
  also removes ConsoleHome, config\, logs\, .git, .grok, .cursor, Users\Default\.airc*,
  ProgramData\Bobiverse\update\airc, and the install manifest itself.
#>
[CmdletBinding()]
param(
    [string]$Nssm = '',
    [string]$InstallRoot = '',
    [string]$ServiceName = 'Airc',
    # FR #3292: MSI AIRC_PURGE=1 / -Purge / workstation manifest default.
    [string]$Purge = '',
    [switch]$PurgeAll
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

Write-Host 'INFO FR #1566: Uninstall-Airc - stop/remove service'

if (-not (Test-BobiverseIsAdmin)) {
    # MSI deferred CA runs elevated; manual runs may need UAC.
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

if (-not $InstallRoot) {
    try { $InstallRoot = Join-Path (Get-BobiverseAiRoot) 'airc' } catch { $InstallRoot = '' }
}

$manPath = Join-Path $env:ProgramData 'Bobiverse\airc-install-manifest.json'
$manifest = $null
if (Test-Path -LiteralPath $manPath) {
    try { $manifest = Get-Content -LiteralPath $manPath -Raw -Encoding utf8 | ConvertFrom-Json } catch { }
}

# Resolve ConsoleHome for log / optional purge (never invent secrets content).
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
if (-not $keptHome -and $manifest -and $manifest.console_home) {
    $keptHome = [string]$manifest.console_home
}

$purgeRaw = ([string]$Purge).Trim().ToLowerInvariant()
$doPurge = [bool]$PurgeAll -or ($purgeRaw -in @('1', 'true', 'yes', 'on'))
if (-not $doPurge -and $manifest -and $manifest.purge_default) { $doPurge = $true }
if (-not $doPurge -and $manifest -and ([string]$manifest.profile).ToLowerInvariant() -eq 'workstation') {
    $doPurge = $true
}

if ($doPurge) {
    Write-Host 'INFO FR #3292 purge uninstall (AIRC_PURGE / workstation default)'
} elseif ($keptHome) {
    Write-Host "INFO keeping ConsoleHome (secrets stay): $keptHome"
} else {
    Write-Host 'INFO ConsoleHome path unknown; fleet default will not delete any profile home'
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
} else {
    try {
        Remove-BobiverseService -Nssm $nssmExe -Name $ServiceName
    } catch {
        # Return=ignore on the MSI CA; still continue so ARP cleanup proceeds.
        Write-Host ("WARN Remove-BobiverseService: {0}" -f $_.Exception.Message)
    }
}

function Remove-AircPathBestEffort {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        Write-Host ("INFO purged {0}" -f $Path)
    } catch {
        Write-Host ("WARN purge {0}: {1}" -f $Path, $_.Exception.Message)
    }
}

if ($doPurge) {
    $targets = New-Object System.Collections.Generic.List[string]
    if ($keptHome) { [void]$targets.Add($keptHome) }
    if ($InstallRoot) {
        foreach ($rel in @('config', 'logs', '.git', '.grok', '.cursor', 'home')) {
            [void]$targets.Add((Join-Path $InstallRoot $rel))
        }
        [void]$targets.Add($InstallRoot)
    }
    if ($manifest -and $manifest.paths) {
        foreach ($p in @($manifest.paths)) {
            if ($p) { [void]$targets.Add([string]$p) }
        }
    }
    [void]$targets.Add((Join-Path $env:ProgramData 'Bobiverse\update\airc'))
    # Legacy Default-profile homes (FR #2355 / #3288).
    foreach ($leaf in @('.airc', '.airc-console')) {
        [void]$targets.Add((Join-Path $env:SystemDrive ('Users\Default\' + $leaf)))
        [void]$targets.Add((Join-Path $env:SystemDrive ('Users\Default\AppData\Local\' + $leaf)))
    }
    foreach ($t in @($targets | Select-Object -Unique)) {
        Remove-AircPathBestEffort -Path $t
    }
    Remove-AircPathBestEffort -Path $manPath
    Write-Host 'INFO FR #3292: Uninstall-Airc purge done'
} else {
    Write-Host 'INFO FR #1566: Uninstall-Airc done (ConsoleHome secrets kept; tree is MSI RemoveFiles)'
}
exit 0
