#Requires -Version 5.1
<#
.SYNOPSIS
  FR #6237 smoke: assert ircBob stdout.log contains "digest http pull ok" after restart.
.DESCRIPTION
  When the digest edge requires a non-default User-Agent, a frozen ear that ignores
  hotpatched scripts/bobreport.py keeps logging "digest http pull failed". After
  prefer-install-scripts (or a rebuilt ear) + Restart-BobEar, this smoke waits for
  the ok line in InstallRoot\logs\stdout.log.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$LogPath = '',
    [int]$TimeoutSec = 90,
    [int]$PollMs = 2000
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$cm = Join-Path $here 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) {
    $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) 'common\scripts\Bobiverse-Common.ps1'
}
if (Test-Path -LiteralPath $cm) { . $cm }
if (-not $InstallRoot) {
    if (Get-Command Get-BobiverseProductRoot -ErrorAction SilentlyContinue) {
        $InstallRoot = Get-BobiverseProductRoot -Product bob
    } else {
        # t780u / FR #6607: never hard-code C:\ai; last-resort is <SystemDrive>\ai\bob
        $sys = if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' }
        $InstallRoot = Join-Path $sys 'ai\bob'
    }
}
if (-not $LogPath) {
    $LogPath = Join-Path $InstallRoot 'logs\stdout.log'
}
$pyHelper = Join-Path $here 'assert_bob_digest_http_pull_ok.py'
if (-not (Test-Path -LiteralPath $pyHelper)) {
    throw "missing $pyHelper"
}
$deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSec))
$python = $null
foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
    if ($c -and (Test-Path -LiteralPath $c)) { $python = $c; break }
}
if (-not $python) { throw 'python.exe not found (Assert-BobDigestHttpPullOk)' }

while ([datetime]::UtcNow -lt $deadline) {
    if (Test-Path -LiteralPath $LogPath) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $python $pyHelper --log $LogPath
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($code -eq 0) {
            Write-Host "OK FR #6237 digest http pull ok seen in $LogPath"
            exit 0
        }
    }
    Start-Sleep -Milliseconds ([Math]::Max(200, $PollMs))
}
Write-Error "FAIL FR #6237: digest http pull ok not seen in $LogPath within ${TimeoutSec}s (frozen ear may still ignore hotpatched bobreport; see prefer_install_scripts_path)"
exit 1
