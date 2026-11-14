#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1481: install or replace scripts\bob-ear.exe with rollback on failure.
.DESCRIPTION
  Copies a built bob-ear.exe into InstallRoot\scripts\, keeping bob-ear.exe.bak for rollback.
  Does not start or stop ircBob (caller owns service lifecycle). Fails closed: on copy/smoke
  failure the previous exe (if any) is restored from .bak.
  FR #7300 / mrb-7311-fix: optional -ProvenancePath copies CI provenance.txt next to the
  exe so Select-BobEarLaunch source= reads the ear component (never install-root MANIFEST).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$SourceExe,
    [string]$ProvenancePath = '',
    [switch]$SkipSmoke
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) { throw "missing source exe: $SourceExe" }
$scripts = Join-Path $InstallRoot 'scripts'
New-Item -ItemType Directory -Force -Path $scripts | Out-Null
$dest = Join-Path $scripts 'bob-ear.exe'
$bak = Join-Path $scripts 'bob-ear.exe.bak'
$provDest = Join-Path $scripts 'provenance.txt'
$provBak = Join-Path $scripts 'provenance.txt.bak'
$hadPrev = Test-Path -LiteralPath $dest -PathType Leaf
$hadProv = Test-Path -LiteralPath $provDest -PathType Leaf
$wroteProv = $false
if ($hadPrev) {
    Copy-Item -LiteralPath $dest -Destination $bak -Force
}
if ($ProvenancePath -and (Test-Path -LiteralPath $ProvenancePath -PathType Leaf) -and $hadProv) {
    Copy-Item -LiteralPath $provDest -Destination $provBak -Force
}
try {
    Copy-Item -LiteralPath $SourceExe -Destination $dest -Force
    if (-not $SkipSmoke) {
        $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $probe = & $dest --help 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        $text = ($probe | Out-String)
        if ($code -ne 0 -or ($text -notmatch 'nick' -and $text -notmatch '--host')) {
            throw "bob-ear.exe smoke failed after install (exit $code): $text"
        }
    }
    if ($ProvenancePath -and (Test-Path -LiteralPath $ProvenancePath -PathType Leaf)) {
        Copy-Item -LiteralPath $ProvenancePath -Destination $provDest -Force
        $wroteProv = $true
    }
    Write-Host ("INFO installed bob-ear.exe -> {0}" -f $dest)
    if ($wroteProv) { Write-Host ("INFO installed ear provenance -> {0}" -f $provDest) }
    return $dest
} catch {
    if ($hadPrev -and (Test-Path -LiteralPath $bak)) {
        Copy-Item -LiteralPath $bak -Destination $dest -Force
        Write-Host 'WARN bob-ear.exe install failed; restored previous bob-ear.exe from .bak'
    } elseif (Test-Path -LiteralPath $dest) {
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    }
    if ($wroteProv) {
        if ($hadProv -and (Test-Path -LiteralPath $provBak)) {
            Copy-Item -LiteralPath $provBak -Destination $provDest -Force
        } elseif (-not $hadProv -and (Test-Path -LiteralPath $provDest)) {
            Remove-Item -LiteralPath $provDest -Force -ErrorAction SilentlyContinue
        }
    }
    throw
}
