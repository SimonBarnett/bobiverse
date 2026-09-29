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
. (Join-Path $scriptDir 'Bobiverse-Common.ps1')
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $scriptDir }
if (-not $ChairHome) {
    if (Test-BobiverseIsLocalSystem) {
        $ChairHome = Join-Path $RepoRoot 'home-jeeves'
    } else {
        $ChairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves'
    }
}
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing' }
}

if (Test-BobiverseIsLocalSystem) { $env:BOBIVERSE_NO_UPDATE = '1' }
[void](Import-BobiverseErgoPassword -InstallRoot $RepoRoot -HomeDir $ChairHome)

$update = Join-Path $scriptDir 'Check-BobiverseUpdate.ps1'
if ((Test-Path -LiteralPath $update) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try {
        & $update -Product jeeves -InstallRoot $RepoRoot
    } catch {
        Write-Host "WARN update-check: $($_.Exception.Message)"
    }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
if (-not (Test-Path -LiteralPath $agent)) { throw "missing $agent" }

$env:BOB_DIGEST_HOME = if ($env:BOB_DIGEST_HOME) { $env:BOB_DIGEST_HOME } else {
    if (Test-BobiverseIsLocalSystem) { Join-Path $RepoRoot 'home' } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
}
New-Item -ItemType Directory -Force -Path $env:BOB_DIGEST_HOME | Out-Null

& $Python -u $agent --chair --nick Jeeves --home $ChairHome
exit $LASTEXITCODE
