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
    [string]$InstallRoot = '',
    # Ergo host the ear connects to. Passed EXPLICITLY on the irc_agent command line (v0.1.20): a process whose
    # command line has no --host is indistinguishable from a stray agent to the tray/watch process matchers,
    # which killed the ear every ~30 s (ionos 06:32-06:51, the repeated "+h" grants). Install-Bob.ps1 bakes it.
    [string]$IrcHost = ''
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
        $BobHome = Join-Path $env:USERPROFILE '.bobiverse'
    }
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null

if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing' }
}

$env:BOB_MACHINE_ID = $MachineId
# Self-update on start: see the v0.1.17 block below (Update-BobiverseService.ps1).

# Ergo server PASS from config\ergo.password / home / env (public MSI no longer embeds - issue #4).
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $BobHome)
if (-not $env:BOB_IRC_PASSWORD) {
    Write-Host 'WARN BOB_IRC_PASSWORD unset - TLS to irc.ntsa.uk will fail without config\ergo.password'
}

# Issue #8: SASL as bob-{machine} so reserved Bob-* nicks get 001 (NickServ account owns the nick).
$nsFile = Join-Path $BobHome 'nickserv.password'
$env:BOB_IRC_SASL_USER = 'bob-' + $MachineId
if (Test-Path -LiteralPath $nsFile) {
    $env:BOB_IRC_SASL_PASSWORD = (Get-Content -LiteralPath $nsFile -Raw).Trim()
    $nsLen = $env:BOB_IRC_SASL_PASSWORD.Length
    Write-Host "INFO SASL user=$($env:BOB_IRC_SASL_USER) from $nsFile (len=$nsLen)"
} else {
    Write-Host "WARN missing $nsFile - reserved nick will fail without BOB_IRC_SASL_PASSWORD"
}

# v0.1.17 self-update on service start: token-less GitHub latest-release check; when newer, a DETACHED
# helper (scheduled task) downloads + sha256-verifies the MSI, replaces the install and rolls back on failure.
# Never blocks or fails the start. Never touches Ergo. Opt out: BOB_AUTOUPDATE=0 (or BOBIVERSE_NO_UPDATE=1).
# BOBIVERSE_REPO (explicit dev opt-in) still fast-forwards that clone into this tree.
$updater = Join-Path $scriptDir 'Update-BobiverseService.ps1'
if (Test-Path -LiteralPath $updater) {
    try { & $updater -Product bob -InstallRoot $InstallRoot -ServiceName ircBob }
    catch { Write-Host "WARN self-update: $($_.Exception.Message)" }
}
$sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
if ($env:BOBIVERSE_REPO -and (Test-Path -LiteralPath $sync) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try { & $sync -Product bob -InstallRoot $InstallRoot }
    catch { Write-Host "WARN sync-from-repo: $($_.Exception.Message)" }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
$shop = "#$MachineId"
$channel = "#bobiverse,$shop"
if (-not $IrcHost) { $IrcHost = [string]$env:BOB_IRC_HOST }
if (-not $IrcHost) { $IrcHost = 'irc.ntsa.uk' }
$IrcHost = $IrcHost.Trim()
if ($IrcHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') { throw "invalid -IrcHost '$IrcHost'" }
Write-Host "INFO ear host=$IrcHost nick=$nick channels=$channel"
& $Python -u $agent --nick $nick --home $BobHome --channel $channel --host $IrcHost
exit $LASTEXITCODE
