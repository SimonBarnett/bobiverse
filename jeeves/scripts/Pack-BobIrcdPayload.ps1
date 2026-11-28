#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9777: stage ergo.exe, default.yaml, and Install-BobIrcd.ps1. No www, no chair MSI.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory)]
    [string]$OutDir
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
& (Join-Path $RepoRoot 'common\scripts\Fetch-Ergo.ps1') -OutDir $OutDir
Copy-Item -LiteralPath (Join-Path $RepoRoot 'jeeves\scripts\Install-BobIrcd.ps1') -Destination (Join-Path $OutDir 'Install-BobIrcd.ps1') -Force
foreach ($need in @('ergo.exe', 'default.yaml', 'Install-BobIrcd.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $OutDir $need))) { throw "IRCD pack missing $need" }
}
if (Test-Path -LiteralPath (Join-Path $OutDir 'www')) { throw 'IRCD pack must not contain www (FR #9777)' }
Get-ChildItem -LiteralPath $OutDir -Recurse -Filter 'jeeves-*.msi' -File -ErrorAction SilentlyContinue | ForEach-Object {
    throw "IRCD pack must not emit $($_.Name) (FR #9777)"
}
Write-Host "INFO IRCD payload at $OutDir"
