#Requires -Version 5.1
<#
.SYNOPSIS
  Report bob-worker agent seat count vs hard cap (FR #3180 report-only).

.DESCRIPTION
  FR #2601 originally queued a seat-heal startworker request when seats were
  below cap. FR #3180 makes seat starts manual only (tray Agent/Plan click,
  explicit !startworker, or a human running bob-worker). This script is now
  report-only: it measures live agent seats and prints missing count. It must
  never write a req-*.json and never start a seat.

.PARAMETER RepoRoot
  Install / tip root that contains tools\BobTrayStartWorker.ps1 (default: parent of scripts).

.PARAMETER DryRun
  Accepted for back-compat; behaviour is always report-only.
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
    throw "FR #3180: missing BobTrayStartWorker.ps1 under $RepoRoot"
}
. $startWorker

$cap = [int]$script:BobTrayHardMaxWorkers
if ($cap -lt 1) { $cap = 2 }
$procs = @(Get-CimInstance Win32_Process -Filter "Name like 'bob-worker%'" -ErrorAction SilentlyContinue |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine)
# Agent seats only (plan/maintenance do not consume the cap) — measure only.
$n = Measure-BobTrayWorkerSeats -Procs $procs -Modes @('agent')
$missing = [Math]::Max(0, $cap - $n)
Write-Output ("FR #3180 Ensure-BobWorkerSeats report-only seats={0} cap={1} missing={2} dryRun={3} (manual only; never queues req)" -f $n, $cap, $missing, [bool]$DryRun)
exit 0
