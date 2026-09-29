#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Bob-{MachineId} ear (NSSM ircBob). Self-update check then irc_agent.
.NOTES
  Issue #3: use --channel (not --channels); load Ergo PASS from MSI config\ergo.password.
  Do not pass -Python via NSSM AppParameters (spaces break quoting) - resolve here.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MachineId,
    [string]$BobHome = '',
    [string]$Python = '',
    [string]$InstallRoot = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'Bobiverse-Common.ps1')

$MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
$nick = "Bob-$MachineId"
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $scriptDir }
if (-not $BobHome) {
    # Prefer profile home when running as a real user; service-local home under LocalSystem (issue #3).
    if (Test-BobiverseIsLocalSystem) {
        $BobHome = Join-Path $InstallRoot 'home'
    } else {
        $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
    }
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null

if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing' }
}

$env:BOB_MACHINE_ID = $MachineId
if (Test-BobiverseIsLocalSystem) {
    $env:BOBIVERSE_NO_UPDATE = '1'
}

# Ergo server PASS from config\ergo.password / home / env (public MSI no longer embeds - issue #4).
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $BobHome)
if (-not $env:AGENTIC_IRC_PASSWORD) {
    Write-Host 'WARN AGENTIC_IRC_PASSWORD unset - TLS to irc.ntsa.uk will fail without config\ergo.password'
}

# Issue #8: SASL as bob-{machine} so reserved Bob-* nicks get 001 (NickServ account owns the nick).
$nsFile = Join-Path $BobHome 'nickserv.password'
$env:AGENTIC_IRC_SASL_USER = 'bob-' + $MachineId
if (Test-Path -LiteralPath $nsFile) {
    $env:AGENTIC_IRC_SASL_PASSWORD = (Get-Content -LiteralPath $nsFile -Raw).Trim()
    $nsLen = $env:AGENTIC_IRC_SASL_PASSWORD.Length
    Write-Host "INFO SASL user=$($env:AGENTIC_IRC_SASL_USER) from $nsFile (len=$nsLen)"
} else {
    Write-Host "WARN missing $nsFile - reserved nick will fail without AGENTIC_IRC_SASL_PASSWORD"
}

$update = Join-Path $scriptDir 'Check-BobiverseUpdate.ps1'
if ((Test-Path -LiteralPath $update) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try { & $update -Product bob -InstallRoot $InstallRoot }
    catch { Write-Host "WARN update-check: $($_.Exception.Message)" }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
$shop = "#$MachineId"
$channel = "#bobiverse,$shop"
& $Python -u $agent --nick $nick --home $BobHome --channel $channel
exit $LASTEXITCODE
