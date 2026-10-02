#Requires -Version 5.1
# t794u: detached helper started by the tray: Restart (stop, wait for STOPPED, start) or Stop an ircBob-style service WITHOUT
# the tray waiting for it. Needs start/stop rights on the service for the interactive user (Install-Bob grants them; see
# Grant-BobiverseServiceUserControl); otherwise it logs access denied and exits 0. ASCII-only for PS 5.1.
[CmdletBinding()]
param(
    [ValidateSet('Stop', 'Restart')][string]$Action = 'Restart',
    [string]$ServiceName = 'ircBob',
    [int]$TimeoutSec = 90,
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'
if ($ServiceName -notmatch '^[A-Za-z0-9_.-]{1,64}$') { exit 2 }
$logDir = Join-Path $env:LOCALAPPDATA 'Bobiverse'
try { New-Item -ItemType Directory -Force -Path $logDir | Out-Null } catch { }
$log = Join-Path $logDir 'tray-service.log'
function Write-SvcLog([string]$m) { try { Add-Content -LiteralPath $log -Value ('{0} {1}' -f (Get-Date).ToString('s'), $m) } catch { } }
$sc = Join-Path $env:SystemRoot 'System32\sc.exe'
function Get-SvcState {
    $o = & $sc query $ServiceName 2>&1 | Out-String
    if ($o -match 'STATE\s*:\s*\d+\s+(\w+)') { return $Matches[1] }
    if ($o -match '1060') { return 'MISSING' }
    return 'UNKNOWN'
}
if ($DryRun) { Write-Output ("dry-run {0} {1}" -f $Action, $ServiceName); exit 0 }
$state = Get-SvcState
if ($state -eq 'MISSING') { Write-SvcLog "$Action ${ServiceName}: service not installed"; exit 0 }
if ($state -ne 'STOPPED') {
    $out = & $sc stop $ServiceName 2>&1 | Out-String
    if ($LASTEXITCODE -eq 5 -or $out -match '(?i)access is denied') {
        Write-SvcLog "$Action ${ServiceName}: access denied (the interactive user has no stop/start right; re-run the installer or Grant-BobiverseServiceUserControl)"
        exit 0
    }
    Write-SvcLog "stop ${ServiceName}: state was $state"
}
if ($Action -eq 'Stop') { exit 0 }
$deadline = [datetime]::UtcNow.AddSeconds($TimeoutSec)
while ([datetime]::UtcNow -lt $deadline) {
    if ((Get-SvcState) -eq 'STOPPED') { break }
    Start-Sleep -Milliseconds 500
}
$out = & $sc start $ServiceName 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Write-SvcLog ("start ${ServiceName} exit {0}: {1}" -f $LASTEXITCODE, ($out -replace '\s+', ' ').Trim()) } else { Write-SvcLog "restarted $ServiceName" }
exit 0