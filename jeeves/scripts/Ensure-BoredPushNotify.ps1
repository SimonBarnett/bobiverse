#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9879: ensure a single watch_bored_push_notify.ps1 is running (dedupe PIDs).
.DESCRIPTION
  Start-JeevesMonitor calls this before launching the MONITORING agent.
  0 running -> Start-Process Hidden; 1 -> leave; >1 -> stop extras (keep oldest).
  -DryRun prints one JSON line and does not spawn/kill.
#>
[CmdletBinding()]
param(
    [string]$Inbound = '',
    [string]$StateDir = '',
    [string]$WatchScript = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $WatchScript) {
    $WatchScript = Join-Path $here 'watch_bored_push_notify.ps1'
}
if (-not (Test-Path -LiteralPath $WatchScript)) {
    Write-Error "missing watch_bored_push_notify.ps1 at $WatchScript"
    exit 2
}
if (-not $StateDir) {
    $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }
    $StateDir = Join-Path $base 'Bobiverse\monitor'
}
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Get-BoredPushNotifyPids {
    $rows = @()
    try {
        foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue)) {
            $cmd = [string]$p.CommandLine
            if (-not $cmd) { continue }
            if ($cmd -notmatch 'watch_bored_push_notify\.ps1') { continue }
            # Skip Ensure itself when its cmdline also cites the watch script path.
            if ($cmd -match 'Ensure-BoredPushNotify\.ps1') { continue }
            $rows += [pscustomobject]@{ Pid = [int]$p.ProcessId; CreationDate = $p.CreationDate }
        }
    } catch { }
    return @($rows | Sort-Object CreationDate)
}

$running = @(Get-BoredPushNotifyPids)
$killed = @()
$started = $false
$kept = @()

if ($running.Count -gt 1) {
    $keep = $running[0]
    $kept = @($keep.Pid)
    foreach ($extra in $running[1..($running.Count - 1)]) {
        if ($DryRun) {
            $killed += $extra.Pid
            continue
        }
        try {
            Stop-Process -Id $extra.Pid -Force -ErrorAction Stop
            $killed += $extra.Pid
        } catch { }
    }
    $running = @(Get-BoredPushNotifyPids)
} elseif ($running.Count -eq 1) {
    $kept = @($running[0].Pid)
}

if ($running.Count -eq 0) {
    $argList = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $WatchScript,
        '-StateDir', $StateDir
    )
    if ($Inbound) { $argList += @('-Inbound', $Inbound) }
    if ($DryRun) {
        $started = $true
    } else {
        try {
            $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -WindowStyle Hidden -PassThru
            $started = $true
            $kept = @([int]$p.Id)
            Start-Sleep -Milliseconds 400
        } catch {
            Write-Error ("failed to start bored-push notify: {0}" -f $_.Exception.Message)
            exit 2
        }
    }
} else {
    $kept = @($running | ForEach-Object { $_.Pid })
}

$payload = [ordered]@{
    ok        = $true
    check     = 'bored_push_notify'
    fr        = 9879
    dry_run   = [bool]$DryRun
    started   = [bool]$started
    kept_pids = @($kept)
    killed_pids = @($killed)
    watch     = $WatchScript
    state_dir = $StateDir
}
$json = ($payload | ConvertTo-Json -Compress)
Write-Output $json
exit 0
