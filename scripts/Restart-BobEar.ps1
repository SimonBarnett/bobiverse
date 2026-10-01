#Requires -Version 5.1
<#
.SYNOPSIS
  Systray / shortcut Restart: announce via running ear if possible, then Restart-Service ircBob.
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'ircBob',
    [string]$Reason = 'tray-restart'
)

$ErrorActionPreference = 'Stop'
Write-Host "INFO restart $ServiceName reason=$Reason"
# Prefer stopping so Start-Bob departure can run on next clean path; signal file for ear.
# Do not use $Home — automatic variable is read-only in PowerShell.
$BobHome = Join-Path $env:USERPROFILE '.bobiverse'
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null
$flag = Join-Path $BobHome 'depart-request.txt'
[IO.File]::WriteAllText($flag, $Reason + "`n", [Text.UTF8Encoding]::new($false))
Start-Sleep -Seconds 2
Restart-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Service $ServiceName | Format-Table Name, Status -AutoSize
