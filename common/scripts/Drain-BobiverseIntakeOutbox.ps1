#Requires -Version 5.1
<#
.SYNOPSIS
  Receipt-aware drain of intake/outbox (FR #2595).

.DESCRIPTION
  Wraps ``python common/scripts/intake.py drain``. Drops do-not-file probes,
  records harvest worker receipts without opening draft PRs, dedupes by
  idempotency key and existing intake/<iid> PRs, and files remaining rows.
  Startup BobCallback drain uses the same Python rules.

.PARAMETER Home
  Bobiverse home that contains intake/outbox (chair/digest home on ionos).

.PARAMETER Limit
  Max outbox JSON files to consider (default 20).

.PARAMETER DryRun
  Count only; leave outbox and GitHub untouched.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Home,
    [int]$Limit = 20,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$intakePy = Join-Path $here 'intake.py'
if (-not (Test-Path -LiteralPath $intakePy)) {
    throw "missing $intakePy"
}
$py = $null
foreach ($c in @('python', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { throw 'python not found on PATH' }

$argList = @($intakePy, 'drain', '--home', $Home, '--limit', [string]$Limit)
if ($DryRun) { $argList += '--dry-run' }
& $py @argList
exit $LASTEXITCODE
