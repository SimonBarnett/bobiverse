#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7510 / #7580: poll the bob digest and write run\tray-digest-pools.json for TipForm/Status.
.DESCRIPTION
  Invoked by bob-tray.exe on a 60s timer (engine alive or not). Pool % for Status/TipForm
  comes only from this file, painted as the digest publishes (no local age stale). UTF-8 no BOM.
  Fetch failure keeps last rows and writes tray-digest-fetch-fail.json for CrashHook. Never prints secrets.
.PARAMETER Root
  Install root (contains run\).
.PARAMETER Url
  Optional digest URL (default Get-BobTrayDigestReportUrl / canonical).
.PARAMETER DigestPath
  Optional fixture JSON path (tests); skips HTTP.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [string]$Url = '',
    [string]$DigestPath = ''
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)

# Resolve BobBridge / Hover helpers (flat install or repo tray tree).
$candidates = @(
    (Join-Path $Root 'src\Public\Get-BobTrayHover.ps1'),
    (Join-Path $Root 'tray\src\Public\Get-BobTrayHover.ps1'),
    (Join-Path (Split-Path $PSScriptRoot -Parent) 'src\Public\Get-BobTrayHover.ps1')
)
$hover = $null
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c -PathType Leaf) { $hover = $c; break }
}
if (-not $hover) { throw 'Get-BobTrayHover.ps1 not found relative to Root/tools' }

$dialogCandidates = @(
    (Join-Path $Root 'tools\BobTrayDialogs.ps1'),
    (Join-Path $PSScriptRoot 'BobTrayDialogs.ps1')
)
. $hover
foreach ($d in $dialogCandidates) {
    if (Test-Path -LiteralPath $d -PathType Leaf) { . $d; break }
}

if (-not (Get-Command Update-BobTrayDigestPools -ErrorAction SilentlyContinue)) {
    throw 'Update-BobTrayDigestPools not loaded'
}

$path = Update-BobTrayDigestPools -Root $Root -Url $Url -DigestPath $DigestPath
if ($path) { Write-Output $path }
