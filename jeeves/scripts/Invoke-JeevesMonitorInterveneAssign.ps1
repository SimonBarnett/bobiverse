<#
.SYNOPSIS
  Ear-relay !assign when idle seats have offerable work (FR #9461 / #9878).
.DESCRIPTION
  Runs tools/monitor/intervene_assign.py. Never edits queue.json, never touches
  Ergo, never Start-BobWorker. Appends UTF-8 no-BOM PRIVMSG lines to the ear
  outbox, or (FR #9878) Jeeves chair outbox shop-wire when cmd-trace is mute /
  -ShopWire is set. Live mute writes to walrus ~/.jeeves/outbox need
  require_machine=walrus; BOB_CHAIR_OUTBOX / -ChairOutbox overrides for tips.
.PARAMETER DryRun
  Plan only; do not write the outbox.
.PARAMETER ForceNeedsHuman
  Allow needs_human rows (default skips them).
.PARAMETER EarOutbox
  Override ear outbox.txt path.
.PARAMETER ChairOutbox
  Override Jeeves outbox for shop-wire (BOB_CHAIR_OUTBOX / ~/.jeeves/outbox.txt).
.PARAMETER ShopWire
  Force shop-wire mode (skip ear !assign).
.PARAMETER PreferShopWireOnMute
  Use shop-wire when cmd-trace stale (default on via idle_seats; opt-in here).
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
    [switch]$ShopWire,
    [switch]$PreferShopWireOnMute,
    [string]$EarOutbox = '',
    [string]$ChairOutbox = '',
    [string]$Fixture = '',
    [string]$InstallRoot = '',
    [string]$ChairHome = '',
    [string]$DigestHome = '',
    [double]$PaceSec = 3.0,
    [double]$CmdTraceMuteSec = 0,
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
if ($ShopWire) { $argv += '--shop-wire' }
if ($PreferShopWireOnMute) { $argv += '--prefer-shop-wire-on-mute' }
if ($EarOutbox) { $argv += @('--ear-outbox', $EarOutbox) }
if ($ChairOutbox) { $argv += @('--chair-outbox', $ChairOutbox) }
if ($Fixture) { $argv += @('--fixture', $Fixture) }
if ($ChairHome) { $argv += @('--chair-home', $ChairHome) }
if ($DigestHome) { $argv += @('--digest-home', $DigestHome) }
if ($PaceSec -gt 0) { $argv += @('--pace-s', ([string]$PaceSec)) }
if ($CmdTraceMuteSec -gt 0) { $argv += @('--cmd-trace-mute-s', ([string]$CmdTraceMuteSec)) }
if ($MaxAssigns -gt 0) { $argv += @('--max-assigns', ([string]$MaxAssigns)) }
$python = if ($env:BOB_PYTHON) { $env:BOB_PYTHON } else { 'python' }
& $python $py @argv
exit $LASTEXITCODE
