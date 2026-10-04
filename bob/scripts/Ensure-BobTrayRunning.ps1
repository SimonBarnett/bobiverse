#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1642: if TipForm / bob-tray is down unexpectedly, relaunch with -ForceNew -SkipTidy only.
.DESCRIPTION
  Watchdog probe for scheduled task BobiverseTrayWatchdog. Always relaunches with -SkipTidy
  (never the TipForm Restart tidy path). Honours tray-watchdog.suppress after intentional
  TipForm Exit. Opt out: BOBIVERSE_TRAY_WATCHDOG=0.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$MachineId = '',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Continue'
if (([string]$env:BOBIVERSE_TRAY_WATCHDOG).Trim() -eq '0') {
    Write-Host 'INFO tray watchdog disabled (BOBIVERSE_TRAY_WATCHDOG=0)'
    exit 0
}

if (-not $InstallRoot) {
    $selfRoot = Split-Path -Parent $PSScriptRoot
    $cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath (Join-Path $selfRoot 'tools\Watch-BobTray.ps1')) { $InstallRoot = $selfRoot }
    elseif (Test-Path -LiteralPath $cm) { . $cm; $InstallRoot = Get-BobiverseProductRoot -Product bob }
    else { $InstallRoot = $selfRoot }
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)

$life = Join-Path $InstallRoot 'tools\BobTrayLifecycle.ps1'
if (Test-Path -LiteralPath $life) { . $life }

if (-not (Get-Command Write-BobTrayLifecycleEvent -ErrorAction SilentlyContinue)) {
    function Write-BobTrayLifecycleEvent {
        param([string]$Event, [hashtable]$Fields = @{})
        try {
            $dir = Join-Path $env:LOCALAPPDATA 'Bobiverse'
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $line = [ordered]@{ ts = (Get-Date).ToUniversalTime().ToString('o'); event = $Event; pid = $PID; user = $env:USERNAME }
            foreach ($k in @($Fields.Keys)) { $line[$k] = $Fields[$k] }
            Add-Content -LiteralPath (Join-Path $dir 'tray-lifecycle.log') -Value (($line | ConvertTo-Json -Compress)) -Encoding utf8
        } catch { }
    }
}
if (-not (Get-Command Test-BobTrayProcessPresent -ErrorAction SilentlyContinue)) {
    function Test-BobTrayProcessPresent {
        param([string]$InstallRoot = '')
        $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                ($_.CommandLine -and ($_.CommandLine -match 'Watch-BobTray\.ps1' -or $_.CommandLine -match '_Watch-BobTray-[^\s"]+\.ps1')) -or
                ($_.Name -eq 'bob-tray.exe')
            })
        return ($hits.Count -gt 0)
    }
}
if (-not (Get-Command Test-BobTrayWatchdogSuppressed -ErrorAction SilentlyContinue)) {
    function Test-BobTrayWatchdogSuppressed { return $false }
}

if (Test-BobTrayProcessPresent -InstallRoot $InstallRoot) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-ok' -Fields @{ installRoot = $InstallRoot }
    Write-Host 'INFO tray watchdog: tray present'
    exit 0
}

if (Test-BobTrayWatchdogSuppressed) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-skip-suppress' -Fields @{ installRoot = $InstallRoot }
    Write-Host 'INFO tray watchdog: suppressed (intentional Exit)'
    exit 0
}

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}

$start = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
if (-not (Test-Path -LiteralPath $start)) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-error' -Fields @{ reason = 'missing-Start-BobTray'; installRoot = $InstallRoot }
    Write-Error "missing $start"
    exit 2
}

Write-BobTrayLifecycleEvent -Event 'watchdog-relaunch' -Fields @{
    installRoot = $InstallRoot
    machineId   = $MachineId
    forceNew    = $true
    skipTidy    = $true
}
Write-Host ("INFO tray watchdog: relaunch Start-BobTray -ForceNew -SkipTidy machine={0}" -f $MachineId)
if ($WhatIf) {
    Write-Host 'INFO WhatIf: would Start-BobTray -ForceNew -SkipTidy'
    exit 0
}
$ps = (Get-Command powershell.exe).Source
# Detached so the scheduled-task instance returns quickly (IgnoreNew + minute watch).
$arg = '-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -MachineId {2} -ForceNew -SkipTidy' -f $start, $InstallRoot, $MachineId
Start-Process -FilePath $ps -ArgumentList $arg -WindowStyle Hidden | Out-Null
exit 0
