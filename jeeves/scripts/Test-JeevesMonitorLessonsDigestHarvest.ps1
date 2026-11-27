[CmdletBinding()]
param([switch]$DryRun, [string]$InstallRoot = '', [string]$ChairHome = '', [string]$DigestHome = '')
& (Join-Path $PSScriptRoot 'Invoke-JeevesMonitorCheck.ps1') -Check lessons_digest_harvest -DryRun:$DryRun -InstallRoot $InstallRoot -ChairHome $ChairHome -DigestHome $DigestHome
exit $LASTEXITCODE
