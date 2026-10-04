#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1481: install or replace scripts\bob-ear.exe with rollback on failure.
.DESCRIPTION
  Copies a built bob-ear.exe into InstallRoot\scripts\, keeping bob-ear.exe.bak for rollback.
  Does not start or stop ircBob (caller owns service lifecycle). Fails closed: on copy/smoke
  failure the previous exe (if any) is restored from .bak.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$SourceExe,
    [switch]$SkipSmoke
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) { throw "missing source exe: $SourceExe" }
$scripts = Join-Path $InstallRoot 'scripts'
New-Item -ItemType Directory -Force -Path $scripts | Out-Null
$dest = Join-Path $scripts 'bob-ear.exe'
$bak = Join-Path $scripts 'bob-ear.exe.bak'
$hadPrev = Test-Path -LiteralPath $dest -PathType Leaf
if ($hadPrev) {
    Copy-Item -LiteralPath $dest -Destination $bak -Force
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
    Write-Host ("INFO installed bob-ear.exe -> {0}" -f $dest)
    return $dest
} catch {
    if ($hadPrev -and (Test-Path -LiteralPath $bak)) {
        Copy-Item -LiteralPath $bak -Destination $dest -Force
        Write-Host 'WARN bob-ear.exe install failed; restored previous bob-ear.exe from .bak'
    } elseif (Test-Path -LiteralPath $dest) {
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    }
    throw
}
