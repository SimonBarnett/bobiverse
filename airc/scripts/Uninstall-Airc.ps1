#Requires -Version 4.0
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
# FR #3516: never take console_home / install_root from the ProgramData manifest -
# a pre-created user-owned manifest can plant C:\ and arbitrary homes.
if (-not $keptHome -and $manifest -and $manifest.console_home) {
    Write-Host 'WARN FR #3516 ignoring manifest.console_home (untrusted); need AppParameters or config\airc-install.json'
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
    # FR #3516: allow-list bases from MSI/arg InstallRoot + trusted ConsoleHome only -
    # never manifest.install_root / manifest.console_home (attacker-controlled).
    $allowInstall = [string]$InstallRoot
    $allowHome = [string]$keptHome
    if ($keptHome) { [void]$targets.Add($keptHome) }
    if ($InstallRoot) {
        foreach ($rel in @('config', 'logs', '.git', '.grok', '.cursor', 'home')) {
            [void]$targets.Add((Join-Path $InstallRoot $rel))
        }
        [void]$targets.Add($InstallRoot)
    }
    if ($manifest -and $manifest.paths) {
        # FR #3394 / #3516: manifest paths only; bases are trusted InstallRoot/ConsoleHome.
        foreach ($p in @($manifest.paths)) {
            if (-not $p) { continue }
            $candidate = [string]$p
            if (Test-BobiverseAircPurgePathAllowed -Path $candidate -InstallRoot $allowInstall -ConsoleHome $allowHome) {
                [void]$targets.Add($candidate)
            } else {
                Write-Host ("WARN FR #3394/#3516 refuse purge path outside allow-list: {0}" -f $candidate)
            }
        }
    }
    [void]$targets.Add((Join-Path $env:ProgramData 'Bobiverse\update\airc'))
    # FR #3392: CA install log + LocalSystem crash spool left behind by MSI / crash hook.
    [void]$targets.Add((Join-Path $env:ProgramData 'Bobiverse\logs\install-airc.log'))
    [void]$targets.Add((Join-Path $env:ProgramData 'Bobiverse\logs'))
    $sysSpool = Join-Path $env:SystemRoot 'System32\config\systemprofile\AppData\Local\Bobiverse\crash-spool'
    [void]$targets.Add($sysSpool)
    [void]$targets.Add((Join-Path $env:SystemRoot 'System32\config\systemprofile\AppData\Local\Bobiverse'))
    # Legacy Default-profile homes (FR #2355 / #3288).
    foreach ($leaf in @('.airc', '.airc-console')) {
        [void]$targets.Add((Join-Path $env:SystemDrive ('Users\Default\' + $leaf)))
        [void]$targets.Add((Join-Path $env:SystemDrive ('Users\Default\AppData\Local\' + $leaf)))
    }
    foreach ($t in @($targets | Select-Object -Unique)) {
        # FR #3516: every purge target (including ConsoleHome) must pass the allow-list.
        if (Test-BobiverseAircPurgePathAllowed -Path $t -InstallRoot $allowInstall -ConsoleHome $allowHome) {
            Remove-AircPathBestEffort -Path $t
        } else {
            Write-Host ("WARN FR #3516 refuse purge target outside allow-list: {0}" -f $t)
        }
    }
    # Manifest file itself lives under ProgramData\Bobiverse (hardcoded allow prefix).
    if (Test-BobiverseAircPurgePathAllowed -Path $manPath -InstallRoot $allowInstall -ConsoleHome $allowHome) {
        Remove-AircPathBestEffort -Path $manPath
    }
    Write-Host 'INFO FR #3292/#3392/#3516: Uninstall-Airc purge done'
} else {
    Write-Host 'INFO FR #1566: Uninstall-Airc done (ConsoleHome secrets kept; tree is MSI RemoveFiles)'
}
exit 0
