#Requires -Version 5.1
<#
.SYNOPSIS
  Download WiX Toolset v3 binaries (candle/light/heat) for packing airc-console MSI.
.NOTES
  Issue #305. Cached under third_party\wix so CI/offline packs work without a
  machine-wide WiX install. Source: wix3 GitHub release binaries zip.
#>
[CmdletBinding()]
param(
    [string]$OutDir = '',
    [string]$CacheDir = '',
    [string]$Url = 'https://github.com/wixtoolset/wix3/releases/download/wix3112rtm/wix311-binaries.zip'
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    if ($PSCommandPath) { $scriptDir = Split-Path -Parent $PSCommandPath }
    elseif ($MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
}
if (-not $CacheDir) {
    if (-not $scriptDir) { throw 'Fetch-Wix: cannot resolve script directory' }
    $repoRoot = Split-Path -Parent $scriptDir
    $CacheDir = Join-Path $repoRoot 'third_party\wix'
}
if (-not $OutDir) { $OutDir = Join-Path $CacheDir 'bin' }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$candle = Join-Path $OutDir 'candle.exe'
$light = Join-Path $OutDir 'light.exe'
$heat = Join-Path $OutDir 'heat.exe'
if ((Test-Path -LiteralPath $candle) -and (Test-Path -LiteralPath $light) -and (Test-Path -LiteralPath $heat)) {
    Write-Host "INFO wix already at $OutDir"
    return $OutDir
}

$zip = Join-Path $CacheDir 'wix311-binaries.zip'
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
if (-not (Test-Path -LiteralPath $zip)) {
    Write-Host "INFO downloading WiX binaries from $Url"
    Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing
}
$extract = Join-Path $CacheDir '_extract'
if (Test-Path -LiteralPath $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

# Zip root may be flat (candle.exe at top) or nested.
$srcCandle = Get-ChildItem -Path $extract -Recurse -Filter candle.exe | Select-Object -First 1
if (-not $srcCandle) { throw "WiX zip missing candle.exe: $zip" }
$srcDir = $srcCandle.Directory.FullName
Copy-Item -Path (Join-Path $srcDir '*') -Destination $OutDir -Recurse -Force
if (-not (Test-Path -LiteralPath $candle)) { throw "Fetch-Wix failed to place candle.exe in $OutDir" }
Write-Host "INFO wix ready at $OutDir"
return $OutDir
