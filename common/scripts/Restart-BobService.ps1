#Requires -Version 5.1
<#
.SYNOPSIS
  Restart ONE Bobiverse Windows service (Start Menu shortcut target). Self-elevates.
.DESCRIPTION
  Only ircJeeves, ircBob or Airc. Never BobIrcd/Ergo (the IRC server) - use a separate, deliberate step for that.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('ircJeeves', 'ircBob', 'Airc')][string]$Service
)
$ErrorActionPreference = 'Stop'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Service', $Service)
    return
}
if (-not (Get-Service -Name $Service -ErrorAction SilentlyContinue)) { throw "service $Service is not installed" }
Restart-Service -Name $Service -Force
Write-Host "INFO restarted $Service -> $((Get-Service -Name $Service).Status)"