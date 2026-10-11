#Requires -Version 5.1
<#
.SYNOPSIS
  Download NSSM 2.24 win64 into a target folder for airc-console release packs.
.NOTES
  Issue #266. NSSM is public domain (https://nssm.cc). Prefer cache under
  third_party\nssm when present so offline packs still work.
  FR #3965: curl/tar helpers; try mirror when nssm.cc returns 503.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OutDir,
    [string]$CacheDir = '',
    [string]$Url = 'https://nssm.cc/release/nssm-2.24.zip',
    # Wayback machine raw capture of the same release zip (nssm.cc often 503).
    [string[]]$MirrorUrls = @(
        'https://web.archive.org/web/20220301000000id_/https://nssm.cc/release/nssm-2.24.zip'
    ),
    # Known sha256 of nssm-2.24.zip (release + archive.org capture).
    [string]$ExpectedSha256 = '727d1e42275c605e0f04aba98095c38a8e1e46def453cdffce42869428aa6743',
    [int]$TimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $PSScriptRoot 'Bobiverse-FetchHelpers.ps1')

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

$candidates = New-Object System.Collections.Generic.List[string]
if ($Url) { [void]$candidates.Add($Url) }
if ($env:BOBIVERSE_NSSM_MIRROR -and $env:BOBIVERSE_NSSM_MIRROR.Trim()) {
    [void]$candidates.Add($env:BOBIVERSE_NSSM_MIRROR.Trim())
}
foreach ($m in @($MirrorUrls)) {
    if ($m -and $m.Trim() -and -not $candidates.Contains($m.Trim())) {
        [void]$candidates.Add($m.Trim())
    }
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('nssm-fetch-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $zip = Join-Path $work 'nssm-2.24.zip'
    $lastErr = $null
    $ok = $false
    foreach ($u in $candidates) {
        try {
            Write-Host "INFO downloading NSSM from $u"
            Invoke-BobiverseDownload -Url $u -OutFile $zip -TimeoutSec $TimeoutSec -UserAgent 'bobiverse-fetch-nssm'
            if ($ExpectedSha256) {
                Assert-BobiverseSha256 -Path $zip -Expected $ExpectedSha256
            }
            $ok = $true
            break
        } catch {
            $lastErr = $_.Exception.Message
            Write-Host "WARN nssm source failed: $lastErr"
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $ok) {
        throw ("nssm download failed from all sources. Last: $lastErr. Seed common/third_party/nssm/win64/nssm.exe or set BOBIVERSE_NSSM_MIRROR.")
    }
    Expand-BobiverseZip -ZipPath $zip -Destination $work
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
                'Bundled for airc-console Install-AircConsole.ps1 (agentic_irc #266).',
                'FR #3965: archive.org mirror when nssm.cc is down; BOBIVERSE_NSSM_MIRROR override.'
            )
        }
    }
    Write-Host "INFO nssm ready at $destExe"
    return $destExe
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
