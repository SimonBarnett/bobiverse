<#
.SYNOPSIS
  Idle seats vs offerable queue (FR #1116 / #8536 / #9461).
.PARAMETER NoIntervene
  Report-only; do not ear-relay !assign on EXIT 1 (FR #9461 default is intervene on).
.PARAMETER InterveneDryRun
  Plan !assign lines without writing the ear outbox.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoIntervene,
    [switch]$InterveneDryRun,
    [switch]$ForceNeedsHuman,
    [string]$EarOutbox = '',
    [string]$InstallRoot = '',
    [string]$ChairHome = '',
    [string]$DigestHome = ''
)
$ErrorActionPreference = 'Stop'
$here = if ($InstallRoot) { $InstallRoot } else { Split-Path -Parent $PSScriptRoot }
$py = Join-Path $here 'tools\monitor\idle_seats.py'
if (-not (Test-Path -LiteralPath $py)) {
    # Fall back to Invoke-JeevesMonitorCheck for older installs without patched idle_seats.
    & (Join-Path $PSScriptRoot 'Invoke-JeevesMonitorCheck.ps1') -Check idle_seats -DryRun:$DryRun -InstallRoot $InstallRoot -ChairHome $ChairHome -DigestHome $DigestHome
    exit $LASTEXITCODE
}
$argv = @()
if ($DryRun) { $argv += '--dry-run' }
if ($NoIntervene) { $argv += '--no-intervene' }
if ($InterveneDryRun) { $argv += '--intervene-dry-run' }
if ($ForceNeedsHuman) { $argv += '--force-needs-human' }
if ($EarOutbox) { $argv += @('--ear-outbox', $EarOutbox) }
if ($ChairHome) { $argv += @('--chair-home', $ChairHome) }
if ($DigestHome) { $argv += @('--digest-home', $DigestHome) }
$python = if ($env:BOB_PYTHON) { $env:BOB_PYTHON } else { 'python' }
& $python $py @argv
exit $LASTEXITCODE
