[CmdletBinding()]
param([switch]$DryRun, [string]$InstallRoot = '', [string]$ChairHome = '', [string]$DigestHome = '')
& (Join-Path $PSScriptRoot 'Invoke-JeevesMonitorCheck.ps1') -Check needs_human_false_positive -DryRun:$DryRun -InstallRoot $InstallRoot -ChairHome $ChairHome -DigestHome $DigestHome
exit $LASTEXITCODE
