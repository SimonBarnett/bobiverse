#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Jeeves chair (used by NSSM ircJeeves). Runs MSI self-update check first.
#>
[CmdletBinding()]
param(
    [string]$ChairHome = '',
    [string]$Python = '',
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $scriptDir }
if (-not $ChairHome) { $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves' }
if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $py) { throw 'python.exe missing' }
    $Python = $py.Source
}

$update = Join-Path $scriptDir 'Check-BobiverseUpdate.ps1'
if (Test-Path -LiteralPath $update) {
    try {
        & $update -Product jeeves -InstallRoot (Split-Path -Parent $scriptDir)
    } catch {
        Write-Host "WARN update-check: $($_.Exception.Message)"
    }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
if (-not (Test-Path -LiteralPath $agent)) { throw "missing $agent" }

$env:BOB_DIGEST_HOME = if ($env:BOB_DIGEST_HOME) { $env:BOB_DIGEST_HOME } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }

& $Python $agent --chair --nick Jeeves --home $ChairHome
exit $LASTEXITCODE
