#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1642: if TipForm / bob-tray is down unexpectedly, relaunch with -ForceNew -SkipTidy only.
.DESCRIPTION
  Watchdog probe for scheduled task BobiverseTrayWatchdog. Always relaunches with -SkipTidy
  (never the TipForm Restart tidy path). Honours tray-watchdog.suppress after intentional
  TipForm Exit. Opt out: BOBIVERSE_TRAY_WATCHDOG=0.
  FR #2585: duplicate bob-tray.exe exits log process-exit reason=already-running (not unexpected).
  FR #3909: prefer Get-Process bob-tray before Win32_Process CIM (CIM can take ~1 min and the
  Interactive scheduled-task host used to flash a blank console for that whole time).
  FR #7505 / FIX #7519: when bob-tray is present but run/tray-status.json is older than 120s
  (frozen TipForm / dead engine), treat as dead - report status-stale, kill, relaunch, log result.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$MachineId = '',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Continue'
$script:TrayStatusStaleSeconds = 120
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
        # FR #3909: fast path - bob-tray.exe is the normal TipForm host.
        if (@(Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue).Count -gt 0) { return $true }
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

function Get-BobTrayStatusSnapPath {
    param([string]$Root)
    return (Join-Path $Root 'run\tray-status.json')
}

function Get-BobTrayStatusAgeSeconds {
    param([string]$Root, [datetime]$Now = [datetime]::UtcNow)
    $snap = Get-BobTrayStatusSnapPath -Root $Root
    if (-not (Test-Path -LiteralPath $snap)) { return [double]::PositiveInfinity }
    try {
        $mtime = (Get-Item -LiteralPath $snap).LastWriteTimeUtc
        return [Math]::Max(0.0, ($Now - $mtime).TotalSeconds)
    } catch {
        return [double]::PositiveInfinity
    }
}

function Invoke-BobTrayEngineReport {
    param(
        [string]$Root,
        [string]$Kind,
        [string]$Machine,
        [string]$ErrorText = '',
        [string]$SnapPath = ''
    )
    $reportPy = Join-Path $Root 'common\scripts\tray_engine_report.py'
    if (-not (Test-Path -LiteralPath $reportPy)) {
        $reportPy = Join-Path (Split-Path $Root -Parent) 'common\scripts\tray_engine_report.py'
    }
    if (-not (Test-Path -LiteralPath $reportPy)) { return }
    $py = (Get-Command python.exe -ErrorAction SilentlyContinue)
    if (-not $py) { $py = Get-Command py.exe -ErrorAction SilentlyContinue }
    if (-not $py) { return }
    $args = @($reportPy, $Kind, '--machine', $Machine)
    if ($SnapPath) { $args += @('--snap', $SnapPath) }
    if ($ErrorText) { $args += @('--error', $ErrorText) }
    try {
        & $py.Source @args | Out-Null
    } catch { }
}

function Stop-BobTrayProcesses {
    param([string]$Root)
    try {
        Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue | ForEach-Object {
            try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    } catch { }
}

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}

# FR #9199 / #9205: intentional park => strip live bob-tray.exe (Watch-only).
# Never Stop-Process bob-tray when it parents TipForm OpenCode seats (seat-exit was=N now=0).
if (Get-Command Remove-BobTrayLiveExeWhileParked -ErrorAction SilentlyContinue) {
    try {
        $parkedEns = Remove-BobTrayLiveExeWhileParked -Root $InstallRoot
        if ($parkedEns.Parked) {
            if ($parkedEns.Removed) {
                Write-Host 'INFO tray watchdog FR #9199 removed live bob-tray.exe (intentional park; Watch-only)'
                Write-BobTrayLifecycleEvent -Event 'watchdog-park-strip-live' -Fields @{ installRoot = $InstallRoot }
            }
            if (Get-Command Stop-BobTrayProcessesProtectingSeats -ErrorAction SilentlyContinue) {
                $stopPark = Stop-BobTrayProcessesProtectingSeats -Root $InstallRoot
                if ($stopPark.SkippedForSeats -gt 0) {
                    Write-Host ('INFO tray watchdog FR #9205 skipped kill bob-tray parenting seats count={0}' -f $stopPark.SkippedForSeats)
                    Write-BobTrayLifecycleEvent -Event 'watchdog-park-skip-kill-seats' -Fields @{
                        installRoot = $InstallRoot
                        skipped     = [int]$stopPark.SkippedForSeats
                        killed      = [int]$stopPark.Killed
                    }
                } elseif ($stopPark.Killed -gt 0) {
                    Write-Host ('INFO tray watchdog FR #9205 stopped bob-tray without seat children killed={0}' -f $stopPark.Killed)
                }
            }
            Start-Sleep -Milliseconds 500
        }
    } catch { }
}

$snapPath = Get-BobTrayStatusSnapPath -Root $InstallRoot
$statusAge = Get-BobTrayStatusAgeSeconds -Root $InstallRoot
$present = Test-BobTrayProcessPresent -InstallRoot $InstallRoot
$frozen = $present -and ($statusAge -ge [double]$script:TrayStatusStaleSeconds)

if ($present -and -not $frozen) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-ok' -Fields @{
        installRoot = $InstallRoot
        statusAgeS  = [int][Math]::Round($statusAge)
    }
    Write-Host 'INFO tray watchdog: tray present'
    exit 0
}

# FR #9146 / #9144: TipForm Exit must not leave ircBob Stopped. Heal the ear even while
# tray-watchdog.suppress is active (TipForm stay-down is intentional; the machine ear is not).
try {
    $irc = Get-Service -Name 'ircBob' -ErrorAction SilentlyContinue
    if ($irc -and $irc.Status -ne 'Running') {
        if (-not $WhatIf) {
            Start-Service -Name 'ircBob' -ErrorAction SilentlyContinue
        }
        Write-BobTrayLifecycleEvent -Event 'ircbob-heal' -Fields @{
            why         = 'stopped-while-tray-exit-suppress'
            via         = 'Ensure-BobTrayRunning'
            installRoot = $InstallRoot
            whatIf      = [bool]$WhatIf
        }
        Write-Host 'INFO tray watchdog: ircBob was Stopped; Start-Service attempted (FR #9146)'
    }
} catch { }

if (Test-BobTrayWatchdogSuppressed) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-skip-suppress' -Fields @{ installRoot = $InstallRoot }
    Write-Host 'INFO tray watchdog: suppressed (intentional Exit)'
    exit 0
}

$start = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
if (-not (Test-Path -LiteralPath $start)) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-error' -Fields @{ reason = 'missing-Start-BobTray'; installRoot = $InstallRoot }
    Write-Error "missing $start"
    exit 2
}

# FR #7505 / FIX #7519: relaunch when absent OR when present with stale tray-status.json.
$relaunchWhy = if ($frozen) { 'status-stale' } else { 'absent' }
if ($frozen) {
    Write-BobTrayLifecycleEvent -Event 'watchdog-status-stale' -Fields @{
        installRoot = $InstallRoot
        machineId   = $MachineId
        statusAgeS  = [int][Math]::Round($statusAge)
        snap        = $snapPath
        thresholdS  = $script:TrayStatusStaleSeconds
    }
    Write-Host ("WARN tray watchdog: tray present but tray-status.json stale age={0}s (threshold={1}s)" -f [int][Math]::Round($statusAge), $script:TrayStatusStaleSeconds)
    Invoke-BobTrayEngineReport -Root $InstallRoot -Kind 'status-stale' -Machine $MachineId -SnapPath $snapPath -ErrorText ("Ensure-BobTrayRunning: tray-status.json age {0}s" -f [int][Math]::Round($statusAge))
    if (-not $WhatIf) {
        Stop-BobTrayProcesses -Root $InstallRoot
        Start-Sleep -Seconds 2
    }
}

Write-BobTrayLifecycleEvent -Event 'watchdog-relaunch' -Fields @{
    installRoot = $InstallRoot
    machineId   = $MachineId
    forceNew    = $true
    skipTidy    = $true
    result      = 'attempt'
    why         = $relaunchWhy
}
Write-Host ("INFO tray watchdog: relaunch Start-BobTray -ForceNew -SkipTidy machine={0} why={1}" -f $MachineId, $relaunchWhy)
if ($WhatIf) {
    Write-Host 'INFO WhatIf: would Start-BobTray -ForceNew -SkipTidy'
    exit 0
}
$ps = (Get-Command powershell.exe).Source
# Detached so the scheduled-task instance returns quickly (IgnoreNew + minute watch).
$arg = '-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}" -MachineId {2} -ForceNew -SkipTidy' -f $start, $InstallRoot, $MachineId
try {
    Start-Process -FilePath $ps -ArgumentList $arg -WindowStyle Hidden -ErrorAction Stop | Out-Null
} catch {
    Write-BobTrayLifecycleEvent -Event 'watchdog-relaunch' -Fields @{
        installRoot = $InstallRoot
        machineId   = $MachineId
        result      = 'fail'
        why         = $relaunchWhy
        error       = $_.Exception.Message
    }
    Invoke-BobTrayEngineReport -Root $InstallRoot -Kind 'relaunch-fail' -Machine $MachineId -SnapPath $snapPath -ErrorText ("Ensure-BobTrayRunning: " + $_.Exception.Message)
    exit 2
}
Start-Sleep -Seconds 8
if (Test-BobTrayProcessPresent -InstallRoot $InstallRoot) {
    $newAge = Get-BobTrayStatusAgeSeconds -Root $InstallRoot
    Write-BobTrayLifecycleEvent -Event 'watchdog-relaunch' -Fields @{
        installRoot = $InstallRoot
        machineId   = $MachineId
        result      = 'ok'
        why         = $relaunchWhy
        statusAgeS  = [int][Math]::Round($newAge)
    }
    Write-Host 'INFO tray watchdog: relaunch ok'
    exit 0
}
Write-BobTrayLifecycleEvent -Event 'watchdog-relaunch' -Fields @{
    installRoot = $InstallRoot
    machineId   = $MachineId
    result      = 'fail'
    why         = $relaunchWhy
    error       = 'tray still absent after Start-BobTray'
}
Write-Host 'WARN tray watchdog: relaunch fail (tray still absent)'
Invoke-BobTrayEngineReport -Root $InstallRoot -Kind 'relaunch-fail' -Machine $MachineId -SnapPath $snapPath -ErrorText 'Ensure-BobTrayRunning: tray still absent after Start-BobTray'
exit 1
