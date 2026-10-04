#Requires -Version 5.1
<#
.SYNOPSIS
  Legacy NSSM entry wrapper for Airc fleet installs (FR #1545).
.DESCRIPTION
  Some boxes still point NSSM AppParameters at Start-AircConsole-Fleet.ps1. The old
  wrapper launched python directly and skipped Sync-BobiverseFromRepo +
  Update-BobiverseService, so VERSION never bumped on Restart-Service.

  This script delegates to Start-AircConsole.ps1 -ServiceMode so the same opt-outs
  (BOBIVERSE_NO_UPDATE / BOB_AUTOUPDATE / config\autoupdate.disabled) apply.
#>
[CmdletBinding()]
param(
    [switch]$ServiceMode,
    [string]$MachineId = '',
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    [string]$OperatorsFile = '',
    [ValidateSet('auto', 'registered', 'domain-lobby')]
    [string]$ShopMode = 'auto',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Python = '',
    [switch]$Sasl,
    [switch]$NoSasl
)
$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$launcher = Join-Path $scriptDir 'Start-AircConsole.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { throw "missing $launcher (FR #1545 Fleet wrapper)" }

# Always ServiceMode under NSSM so Update-BobiverseService runs (FR #1545).
$args = @{
    ServiceMode  = $true
    ShopMode     = $ShopMode
    HostName     = $HostName
    Port         = $Port
}
if ($MachineId) { $args['MachineId'] = $MachineId }
if ($ConsoleHome) { $args['ConsoleHome'] = $ConsoleHome }
if ($PasswordFile) { $args['PasswordFile'] = $PasswordFile }
if ($OperatorsFile) { $args['OperatorsFile'] = $OperatorsFile }
if ($Python) { $args['Python'] = $Python }
if ($PSBoundParameters.ContainsKey('Sasl')) { $args['Sasl'] = $Sasl }
if ($NoSasl) { $args['NoSasl'] = $true }

Write-Host "INFO Fleet wrapper FR #1545 delegates to Start-AircConsole.ps1 -ServiceMode (sync+self-update)"
& $launcher @args
exit $LASTEXITCODE
