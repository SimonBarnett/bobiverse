#Requires -Version 5.1
<#
.SYNOPSIS
  Prompt for Windows password and set NSSM ObjectName for ircBob / ircJeeves (DPAPI user).
.NOTES
  Use after MSI when BOBIVERSE_SERVICE_PASSWORD was not set (issue #3).
#>
[CmdletBinding()]
param(
    [ValidateSet('bob', 'jeeves', 'airc')]
    [string]$Product = 'bob',
    [string]$ServiceName = '',
    [string]$InstallRoot = '',
    [string]$User = '',
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'Bobiverse-Common.ps1')

if (-not (Test-BobiverseIsAdmin)) {
    Request-BobiverseUacRelaunch -Bound $PSBoundParameters
}

if (-not $InstallRoot) { $InstallRoot = Join-Path 'C:\ai' $Product }
if (-not $ServiceName) {
    $ServiceName = switch ($Product) {
        'bob' { 'ircBob' }
        'jeeves' { 'ircJeeves' }
        'airc' { 'Airc' }
    }
}

$Nssm = Resolve-BobiverseNssm -ScriptDir $here
if (-not $Nssm) { throw 'nssm missing' }
if (-not $User) { $User = Resolve-BobiverseServiceUser }
if (-not $User) { throw 'cannot resolve service user' }

$ok = Set-BobiverseServiceObjectName -Nssm $Nssm -ServiceName $ServiceName -User $User `
    -InstallRoot $InstallRoot -PromptIfMissing
if (-not $ok) { throw "ObjectName password not set for $ServiceName" }

if (-not $NoStart) {
    Restart-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host "INFO Complete-BobiverseServiceLogon done $ServiceName as $User"
