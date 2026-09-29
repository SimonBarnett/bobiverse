#Requires -Version 5.1
<#
.SYNOPSIS
  Download Ergo Windows x86_64 release into a cache/out folder for jeeves MSI packs.
.NOTES
  Default v2.19.1 (matches fleet irc.ntsa.uk). License: MIT (Ergo / Oragono).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OutDir,
    [string]$CacheDir = '',
    [string]$Version = '2.19.1',
    [string]$Url = ''
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$destExe = Join-Path $OutDir 'ergo.exe'
if ((Test-Path -LiteralPath $destExe) -and (Test-Path -LiteralPath (Join-Path $OutDir 'default.yaml'))) {
    Write-Host "INFO ergo already at $destExe"
    return $OutDir
}

if (-not $CacheDir) {
    if ($PSScriptRoot) {
        $repoRoot = Split-Path -Parent $PSScriptRoot
        $CacheDir = Join-Path $repoRoot 'third_party\ergo'
    }
}
$cacheRoot = $null
if ($CacheDir) {
    foreach ($rel in @("win64", "ergo-$Version-windows-x86_64", '.')) {
        $c = Join-Path $CacheDir $rel
        if (Test-Path -LiteralPath (Join-Path $c 'ergo.exe')) { $cacheRoot = $c; break }
    }
}
if ($cacheRoot) {
    Copy-Item -Path (Join-Path $cacheRoot '*') -Destination $OutDir -Recurse -Force
    Write-Host "INFO ergo copied from cache $cacheRoot"
    return $OutDir
}

if (-not $Url) {
    $Url = "https://github.com/ergochat/ergo/releases/download/v$Version/ergo-$Version-windows-x86_64.zip"
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('ergo-fetch-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $zip = Join-Path $work 'ergo.zip'
    Write-Host "INFO downloading Ergo from $Url"
    Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 300
    Expand-Archive -LiteralPath $zip -DestinationPath $work -Force
    $found = Get-ChildItem -Path $work -Recurse -Filter 'ergo.exe' | Select-Object -First 1
    if (-not $found) { throw 'ergo.exe not found inside downloaded zip' }
    $srcDir = $found.Directory.FullName
    Copy-Item -Path (Join-Path $srcDir '*') -Destination $OutDir -Recurse -Force
    if ($CacheDir) {
        $cacheWin64 = Join-Path $CacheDir 'win64'
        New-Item -ItemType Directory -Force -Path $cacheWin64 | Out-Null
        Copy-Item -Path (Join-Path $srcDir '*') -Destination $cacheWin64 -Recurse -Force
        $lic = Join-Path $CacheDir 'README.txt'
        if (-not (Test-Path -LiteralPath $lic)) {
            Set-Content -LiteralPath $lic -Encoding ascii -Value @(
                "Ergo $Version (windows-x86_64)",
                "Source: $Url",
                'License: see LICENSE in win64/',
                'Bundled for bobiverse jeeves MSI / Install-BobIrcd.ps1.'
            )
        }
    }
    Write-Host "INFO ergo ready at $destExe"
    return $OutDir
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
