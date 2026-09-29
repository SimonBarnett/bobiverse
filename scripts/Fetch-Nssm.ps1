#Requires -Version 5.1
<#
.SYNOPSIS
  Download NSSM 2.24 win64 into a target folder for airc-console release packs.
.NOTES
  Issue #266. NSSM is public domain (https://nssm.cc). Prefer cache under
  third_party\nssm when present so offline packs still work.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OutDir,
    [string]$CacheDir = '',
    [string]$Url = 'https://nssm.cc/release/nssm-2.24.zip'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$destExe = Join-Path $OutDir 'nssm.exe'
if (Test-Path -LiteralPath $destExe) {
    Write-Host "INFO nssm already at $destExe"
    return $destExe
}

if (-not $CacheDir) {
    if ($PSScriptRoot) {
        $repoRoot = Split-Path -Parent $PSScriptRoot
        $CacheDir = Join-Path $repoRoot 'third_party\nssm'
    }
}
$cacheExe = $null
if ($CacheDir) {
    foreach ($rel in @('win64\nssm.exe', 'nssm.exe')) {
        $c = Join-Path $CacheDir $rel
        if (Test-Path -LiteralPath $c) { $cacheExe = $c; break }
    }
}
if ($cacheExe) {
    Copy-Item -LiteralPath $cacheExe -Destination $destExe -Force
    Write-Host "INFO nssm copied from cache $cacheExe"
    return $destExe
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('nssm-fetch-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $zip = Join-Path $work 'nssm-2.24.zip'
    Write-Host "INFO downloading NSSM from $Url"
    Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 120
    Expand-Archive -LiteralPath $zip -DestinationPath $work -Force
    $found = Get-ChildItem -Path $work -Recurse -Filter 'nssm.exe' |
        Where-Object { $_.FullName -match '\\win64\\nssm\.exe$' } |
        Select-Object -First 1
    if (-not $found) {
        $found = Get-ChildItem -Path $work -Recurse -Filter 'nssm.exe' | Select-Object -First 1
    }
    if (-not $found) { throw 'nssm.exe not found inside downloaded zip' }
    Copy-Item -LiteralPath $found.FullName -Destination $destExe -Force
    if ($CacheDir) {
        $cacheWin64 = Join-Path $CacheDir 'win64'
        New-Item -ItemType Directory -Force -Path $cacheWin64 | Out-Null
        Copy-Item -LiteralPath $found.FullName -Destination (Join-Path $cacheWin64 'nssm.exe') -Force
        $lic = Join-Path $CacheDir 'README.txt'
        if (-not (Test-Path -LiteralPath $lic)) {
            Set-Content -LiteralPath $lic -Encoding ascii -Value @(
                'NSSM (Non-Sucking Service Manager) 2.24',
                'Source: https://nssm.cc/release/nssm-2.24.zip',
                'License: public domain (see https://nssm.cc)',
                'Bundled for airc-console Install-AircConsole.ps1 (agentic_irc #266).'
            )
        }
    }
    Write-Host "INFO nssm ready at $destExe"
    return $destExe
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
