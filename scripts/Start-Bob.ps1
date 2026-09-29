#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Bob-{MachineId} ear (NSSM ircBob). Self-update check then irc_agent.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MachineId,
    [string]$BobHome = '',
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
$nick = "Bob-$MachineId"
if (-not $BobHome) { $BobHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $py) { throw 'python.exe missing' }
    $Python = $py.Source
}

$env:BOB_MACHINE_ID = $MachineId

$update = Join-Path $scriptDir 'Check-BobiverseUpdate.ps1'
if (Test-Path -LiteralPath $update) {
    try { & $update -Product bob -InstallRoot (Split-Path -Parent $scriptDir) }
    catch { Write-Host "WARN update-check: $($_.Exception.Message)" }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
$shop = "#$MachineId"
& $Python $agent --nick $nick --home $BobHome --channels "#bobiverse,$shop"
exit $LASTEXITCODE
