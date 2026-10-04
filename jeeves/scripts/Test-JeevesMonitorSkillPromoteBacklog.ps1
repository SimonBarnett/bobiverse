#Requires -Version 5.1
param([switch]$DryRun, [string]$InstallRoot = '', [string]$ChairHome = '', [string]$DigestHome = '')
& (Join-Path $PSScriptRoot 'Invoke-JeevesMonitorCheck.ps1') -Check skill_promote_backlog -DryRun:$DryRun -InstallRoot $InstallRoot -ChairHome $ChairHome -DigestHome $DigestHome
exit $LASTEXITCODE
