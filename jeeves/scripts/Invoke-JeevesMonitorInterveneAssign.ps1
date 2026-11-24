<#
.SYNOPSIS
  Ear-relay !assign when idle seats have offerable work (FR #9461).
.DESCRIPTION
  Runs tools/monitor/intervene_assign.py. Never edits queue.json, never touches
  Ergo, never Start-BobWorker. Appends UTF-8 no-BOM PRIVMSG lines to the ear outbox.
.PARAMETER DryRun
  Plan only; do not write the outbox.
.PARAMETER ForceNeedsHuman
  Allow needs_human rows (default skips them).
.PARAMETER EarOutbox
  Override ear outbox.txt path.
.PARAMETER Fixture
  JSON fixture path (idle_seats + unaccepted) for offline tests.
.PARAMETER TruncateOutbox
  Truncate outbox when companion *.pos is at EOF.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$ForceNeedsHuman,
    [switch]$TruncateOutbox,
    [string]$EarOutbox = '',
    [string]$Fixture = '',
    [string]$InstallRoot = '',
    [string]$ChairHome = '',
    [string]$DigestHome = '',
    [double]$PaceSec = 3.0,
    [int]$MaxAssigns = 8
)
$ErrorActionPreference = 'Stop'
$here = if ($InstallRoot) { $InstallRoot } else { Split-Path -Parent $PSScriptRoot }
$py = Join-Path $here 'tools\monitor\intervene_assign.py'
if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "missing $py"
    exit 2
}
$argv = @()
if ($DryRun) { $argv += '--intervene-dry-run' }  # plan-only; never pass --dry-run (that early-exits empty without --fixture)
if ($ForceNeedsHuman) { $argv += '--force-needs-human' }
if ($TruncateOutbox) { $argv += '--truncate-outbox' }
if ($EarOutbox) { $argv += @('--ear-outbox', $EarOutbox) }
if ($Fixture) { $argv += @('--fixture', $Fixture) }
if ($ChairHome) { $argv += @('--chair-home', $ChairHome) }
if ($DigestHome) { $argv += @('--digest-home', $DigestHome) }
if ($PaceSec -gt 0) { $argv += @('--pace-s', ([string]$PaceSec)) }
if ($MaxAssigns -gt 0) { $argv += @('--max-assigns', ([string]$MaxAssigns)) }
$python = if ($env:BOB_PYTHON) { $env:BOB_PYTHON } else { 'python' }
& $python $py @argv
exit $LASTEXITCODE
