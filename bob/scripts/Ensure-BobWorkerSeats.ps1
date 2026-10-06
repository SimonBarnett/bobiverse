#Requires -Version 5.1
<#
.SYNOPSIS
  Top bob-worker agent seats up to the hard cap of 2 (FR #2601).

.DESCRIPTION
  After irc-lost (bob-worker exit=3) a seat dies cleanly with no crash hook.
  TipForm bob-tray.exe Watchdog also heals seats (seat-heal lifecycle). This
  script measures live seats with Measure-BobTrayWorkerSeats and, when below
  cap, queues one !startworker-style req-*.json for the tray to launch.
  Never starts above BobTrayHardMaxWorkers (2). Never queues Plan seats.
  Opt out: BOBIVERSE_WORKER_SEAT_HEAL=0.

.PARAMETER RepoRoot
  Install / tip root that contains tools\BobTrayStartWorker.ps1 (default: parent of scripts).

.PARAMETER DryRun
  Report missing seats only; do not queue a start.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/')

$startWorker = Join-Path $RepoRoot 'tools\BobTrayStartWorker.ps1'
if (-not (Test-Path -LiteralPath $startWorker)) {
    $alt = Join-Path $RepoRoot 'tray\tools\BobTrayStartWorker.ps1'
    if (Test-Path -LiteralPath $alt) { $startWorker = $alt }
}
if (-not (Test-Path -LiteralPath $startWorker)) {
    throw "FR #2601: missing BobTrayStartWorker.ps1 under $RepoRoot"
}
. $startWorker

$cap = [int]$script:BobTrayHardMaxWorkers
if ($cap -lt 1) { $cap = 2 }
$procs = @(Get-CimInstance Win32_Process -Filter "Name like 'bob-worker%'" -ErrorAction SilentlyContinue |
        Select-Object ProcessId, ParentProcessId, Name)
$n = Measure-BobTrayWorkerSeats -Procs $procs
$missing = [Math]::Max(0, $cap - $n)
Write-Output ("FR #2601 Ensure-BobWorkerSeats seats={0} cap={1} missing={2} dryRun={3}" -f $n, $cap, $missing, [bool]$DryRun)

if ($missing -le 0) { exit 0 }
if (("" + $env:BOBIVERSE_WORKER_SEAT_HEAL).Trim() -eq '0') {
    Write-Output 'seat-heal disabled (BOBIVERSE_WORKER_SEAT_HEAL=0)'
    exit 0
}
if ($DryRun) { exit 0 }

$refuse = Get-BobTrayWorkerCapRefusal
if ($refuse) {
    Write-Warning $refuse
    exit 0
}

$dir = Get-BobTrayStartWorkerDir -Root $RepoRoot
if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$rid = ('{0:yyyyMMdd-HHmmss}-{1}' -f [datetime]::UtcNow, ([guid]::NewGuid().ToString('N').Substring(0, 6)))
$body = @{
    id      = $rid
    mode    = 'agent'
    by      = 'Ensure-BobWorkerSeats'
    kind    = 'seat-heal'
    ts      = [int64]$now
    expires = [int64]($now + 60)
} | ConvertTo-Json -Compress
$tmp = Join-Path $dir ('.req-{0}.tmp' -f $rid)
$dst = Join-Path $dir ('req-{0}.json' -f $rid)
Set-Content -LiteralPath $tmp -Value $body -Encoding utf8
Move-Item -LiteralPath $tmp -Destination $dst -Force
Write-Output ("queued startworker mode=agent id={0} dir={1}" -f $rid, $dir)
exit 0
