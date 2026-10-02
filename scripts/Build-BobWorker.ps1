#Requires -Version 5.1
<#
.SYNOPSIS
  Compile scripts\bob_worker.py into bob-worker.exe (PyInstaller, one file). Called by Pack-BobiverseRelease.ps1 for the bob MSI.
.DESCRIPTION
  The repo toolchain is Python (every service is a .py run by NSSM), so the worker is frozen with PyInstaller rather than
  introducing a second toolchain. Needs Python 3.12 + `pip install pyinstaller` on the BUILD machine only; the target box needs
  neither (the exe embeds its own interpreter). The exe is a console-subsystem program (the tray starts it hidden).
.OUTPUTS
  The full path of the built bob-worker.exe.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$src = Join-Path $RepoRoot 'scripts\bob_worker.py'
if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
if (-not $Python) {
    foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
        if ($c -and (Test-Path -LiteralPath $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw 'python.exe not found (needed to build bob-worker.exe)' }
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $Python -m PyInstaller --version *> $null
$pyiOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $pyiOk) { throw "PyInstaller missing for $Python (pip install pyinstaller)" }

$work = Join-Path $OutDir 'worker-build'
if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$dist = Join-Path $work 'dist'
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$log = & $Python -m PyInstaller --noconfirm --clean --onefile --console --name bob-worker `
    --distpath $dist --workpath (Join-Path $work 'build') --specpath $work `
    --paths (Join-Path $RepoRoot 'scripts') --exclude-module numpy --exclude-module pandas --exclude-module matplotlib `
    $src 2>&1
$code = $LASTEXITCODE
$ErrorActionPreference = $prevEap
$exe = Join-Path $dist 'bob-worker.exe'
if ($code -ne 0 -or -not (Test-Path -LiteralPath $exe)) {
    ($log | Select-Object -Last 25) | ForEach-Object { Write-Host "  pyinstaller: $_" }
    throw "PyInstaller failed (exit $code)"
}
# Smoke: the frozen exe must start and run its selection logic without starting any agent.
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$probe = & $exe --dry-run --install-root $work 2>&1
$pcode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($pcode -ne 0 -or -not (($probe | Out-String) -match '"decision"')) { throw "bob-worker.exe smoke test failed (exit $pcode): $($probe | Out-String)" }
Write-Host ("INFO built {0} ({1:N1} MB)" -f $exe, ((Get-Item -LiteralPath $exe).Length / 1MB))
$exe