#Requires -Version 5.1
<#
.SYNOPSIS
  Public launcher for the TipForm Bob systray shipped in the bob MSI.
.DESCRIPTION
  Sets BOB_MACHINE_ID / BOB_BRIDGE_HOME / IRC home, then starts tools\Watch-BobTray.ps1
  under InstallRoot (STA). Companion to the ircBob Windows service — not a BobFleet task.
.NOTES
  CAST IRON: product Sync/ff runs only on ircBob service start (Start-Bob).
  This launcher always passes -SkipUpdate to Start-BobFleetTray.
  TipForm menu Restart calls Restart-BobEar (service recycle -> Start-Bob Sync/ff),
  then relaunches the tray watcher in the interactive session.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\ai\bob',
    [string]$ServiceName = 'ircBob',
    [string]$BobHome = '',
    [string]$MachineId = '',
    [switch]$ForceNew
)

$ErrorActionPreference = 'Continue'

if (-not $InstallRoot) { $InstallRoot = 'C:\ai\bob' }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)

$tray = Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'
if (-not (Test-Path -LiteralPath $tray)) {
    # Dev fallback: vendored tree next to scripts\
    $repo = Split-Path -Parent $PSScriptRoot
    $alt = Join-Path $repo 'third_party\bob-tray\tools\Watch-BobTray.ps1'
    if (Test-Path -LiteralPath $alt) {
        $InstallRoot = [IO.Path]::GetFullPath((Join-Path $repo 'third_party\bob-tray'))
        $tray = Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'
    }
}
if (-not (Test-Path -LiteralPath $tray)) {
    Write-Error "missing TipForm tray: $InstallRoot\tools\Watch-BobTray.ps1 (run Sync-BobTrayFromAgenticBuild / pack bob)"
    exit 1
}

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
} else {
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}

if (-not $BobHome) {
    $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
}
$bridge = Join-Path $env:USERPROFILE '.grok\bob-bridge'
New-Item -ItemType Directory -Force -Path $BobHome, $bridge | Out-Null

$env:BOB_MACHINE_ID = $MachineId
$env:BOB_BRIDGE_HOME = $bridge
$env:BOB_IRC_HOME = $BobHome
$env:AGENTIC_IRC_HOME = $BobHome
if (-not $env:BOBIVERSE_BOB_VERSION) {
    foreach ($vf in @(
            (Join-Path $InstallRoot 'VERSION'),
            (Join-Path (Split-Path -Parent $PSScriptRoot) 'src\VERSION'),
            'C:\ai\bob\VERSION'
        )) {
        if ($vf -and (Test-Path -LiteralPath $vf)) {
            $env:BOBIVERSE_BOB_VERSION = ([string](Get-Content -LiteralPath $vf -TotalCount 1)).Trim()
            break
        }
    }
}

# One TipForm only: stop other Watch-BobTray / seat wrappers (and legacy minimal Start-BobTray hosts).
$prior = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and [int]$_.ProcessId -ne $PID -and (
            $_.CommandLine -match 'Watch-BobTray\.ps1' -or
            $_.CommandLine -match '_Watch-BobTray-[^\s"]+\.ps1' -or
            ($_.CommandLine -match 'Start-BobTray\.ps1' -and $_.CommandLine -notmatch [regex]::Escape($MyInvocation.MyCommand.Path))
        )
    })
if ($ForceNew -or $prior.Count -gt 0) {
    foreach ($p in $prior) {
        try {
            Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
            Write-Host ("INFO stopped prior tray pid={0}" -f $p.ProcessId)
        } catch { }
    }
    Start-Sleep -Milliseconds 600
}

# Prefer Start-BobFleetTray when present (tidy + MSI update stub); else Watch-BobTray direct.
$fleetStart = Join-Path $InstallRoot 'tools\Start-BobFleetTray.ps1'
if (Test-Path -LiteralPath $fleetStart) {
    & $fleetStart -RepoRoot $InstallRoot -SkipUpdate -ForceNew:$ForceNew
    exit $LASTEXITCODE
}

& $tray -RepoRoot $InstallRoot
exit $LASTEXITCODE
