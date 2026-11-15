#Requires -Version 5.1
<#
.SYNOPSIS
  FR #1481 / #7390 / #7394: install or replace scripts\bob-ear.exe (+ ear launchers) with rollback on failure.
.DESCRIPTION
  Copies a built bob-ear.exe into InstallRoot\scripts\, keeping bob-ear.exe.bak for rollback.
  Does not start or stop ircBob (caller owns service lifecycle). Fails closed: on copy/smoke
  failure the previous exe (if any) is restored from .bak.
  FR #7584: copy companion artifact files before smoke; never smoke the exe alone.
  FR #7300 / mrb-7311-fix: optional -ProvenancePath copies CI provenance.txt next to the
  exe so Select-BobEarLaunch source= reads the ear component (never install-root MANIFEST).
  FR #7390 / #7394: when Start-Bob.ps1 / Select-BobEarLaunch.ps1 / Bobiverse-Common.ps1
  sit beside SourceExe (CI artifact), copy them into scripts\ too, verify SHA-256 against
  provenance keys when present, and roll them back with the exe on failure.
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
$srcDir = Split-Path -Parent $SourceExe

# FR #7390 / #7394: launcher names in the CI artifact (siblings of bob-ear.exe).
$launcherSpecs = @(
    @{ Name = 'Start-Bob.ps1'; ProvKey = 'start_bob_ps1_sha256' },
    @{ Name = 'Select-BobEarLaunch.ps1'; ProvKey = 'select_bob_ear_launch_ps1_sha256' },
    @{ Name = 'Bobiverse-Common.ps1'; ProvKey = 'bobiverse_common_ps1_sha256' },
    @{ Name = 'bobreport.py'; ProvKey = 'runtime_bobreport_py_sha256' },
    @{ Name = 'opencode_fuel.py'; ProvKey = 'runtime_opencode_fuel_py_sha256' }
)

function Get-ProvHashMap {
    param([string]$Path)
    $map = @{}
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $map }
    Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | ForEach-Object {
        $line = [string]$_
        if ($line -match '^\s*([A-Za-z0-9_]+)\s*=\s*([0-9a-fA-F]{64})\s*$') {
            $map[$Matches[1]] = $Matches[2].ToLowerInvariant()
        }
    }
    return $map
}

function Assert-FileSha256 {
    param([string]$Path, [string]$Expected, [string]$Label)
    if (-not $Expected) { return }
    $got = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($got -ne $Expected.ToLowerInvariant()) {
        throw ("FR #7390 {0} sha256 mismatch: got {1} expected {2}" -f $Label, $got, $Expected)
    }
}

$provMap = Get-ProvHashMap -Path $ProvenancePath
$launcherPlan = @()
foreach ($spec in $launcherSpecs) {
    $src = Join-Path $srcDir $spec.Name
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { continue }
    $want = $provMap[$spec.ProvKey]
    Assert-FileSha256 -Path $src -Expected $want -Label $spec.Name
    $launcherPlan += [pscustomobject]@{
        Name    = $spec.Name
        Source  = $src
        Dest    = Join-Path $scripts $spec.Name
        Bak     = Join-Path $scripts ($spec.Name + '.bak')
        WantSha = $want
        HadPrev = (Test-Path -LiteralPath (Join-Path $scripts $spec.Name) -PathType Leaf)
        Wrote   = $false
    }
}

if ($hadPrev) {
    Copy-Item -LiteralPath $dest -Destination $bak -Force
}
if ($ProvenancePath -and (Test-Path -LiteralPath $ProvenancePath -PathType Leaf) -and $hadProv) {
    Copy-Item -LiteralPath $provDest -Destination $provBak -Force
}
foreach ($row in $launcherPlan) {
    if ($row.HadPrev) {
        Copy-Item -LiteralPath $row.Dest -Destination $row.Bak -Force
    }
}

try {
    # FR #7584: stage exe + all companion artifacts first; smoke only when the layout is complete.
    Copy-Item -LiteralPath $SourceExe -Destination $dest -Force
    foreach ($row in $launcherPlan) {
        Copy-Item -LiteralPath $row.Source -Destination $row.Dest -Force
        Assert-FileSha256 -Path $row.Dest -Expected $row.WantSha -Label $row.Name
        $row.Wrote = $true
        Write-Host ("INFO installed ear launcher -> {0}" -f $row.Dest)
    }
    if ($ProvenancePath -and (Test-Path -LiteralPath $ProvenancePath -PathType Leaf)) {
        Copy-Item -LiteralPath $ProvenancePath -Destination $provDest -Force
        $wroteProv = $true
    }
    if (-not $SkipSmoke) {
        foreach ($row in $launcherPlan) {
            if (-not (Test-Path -LiteralPath $row.Dest -PathType Leaf)) {
                throw ("bob-ear.exe smoke refused: missing companion {0}" -f $row.Name)
            }
        }
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
    if ($wroteProv) { Write-Host ("INFO installed ear provenance -> {0}" -f $provDest) }
    return $dest
} catch {
    if ($hadPrev -and (Test-Path -LiteralPath $bak)) {
        Copy-Item -LiteralPath $bak -Destination $dest -Force
        Write-Host 'WARN bob-ear.exe install failed; restored previous bob-ear.exe from .bak'
    } elseif (Test-Path -LiteralPath $dest) {
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    }
    foreach ($row in $launcherPlan) {
        if (-not $row.Wrote) { continue }
        if ($row.HadPrev -and (Test-Path -LiteralPath $row.Bak)) {
            Copy-Item -LiteralPath $row.Bak -Destination $row.Dest -Force
            Write-Host ("WARN restored previous ear launcher from .bak -> {0}" -f $row.Name)
        } elseif (-not $row.HadPrev -and (Test-Path -LiteralPath $row.Dest)) {
            Remove-Item -LiteralPath $row.Dest -Force -ErrorAction SilentlyContinue
        }
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
