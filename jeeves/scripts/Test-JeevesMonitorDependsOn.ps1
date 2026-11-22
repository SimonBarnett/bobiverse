[CmdletBinding()]
param([switch]$DryRun, [string]$InstallRoot = '', [string]$ChairHome = '', [string]$DigestHome = '')
& (Join-Path $PSScriptRoot 'Invoke-JeevesMonitorCheck.ps1') -Check depends_on -DryRun:$DryRun -InstallRoot $InstallRoot -ChairHome $ChairHome -DigestHome $DigestHome
exit $LASTEXITCODE
