#Requires -Version 5.1
<#
.SYNOPSIS
  Compile scripts\bob_worker.py into bob-worker.exe (PyInstaller, one file). Called by Pack-BobiverseRelease.ps1 for the bob MSI.
.DESCRIPTION
  The repo toolchain is Python (every service is a .py run by NSSM), so the worker is frozen with PyInstaller rather than
  introducing a second toolchain. Needs Python 3.12 + `pip install pyinstaller` on the BUILD machine only; the target box needs
  neither (the exe embeds its own interpreter). The exe is a console-subsystem program: its console window IS the one agent window (the tray starts it with a visible console; the agent inherits it).
.OUTPUTS
  The full path of the built bob-worker.exe.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
# t773u: repo is split per service (this script is bob\scripts); a flat stage keeps it next to Bobiverse-Common.ps1.
$cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) { $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Bobiverse-Common.ps1' }
. $cm
if (-not $RepoRoot) { $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot }
$src = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\bob_worker.py'
if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
# PyInstaller needs every scripts dir on its path (the composed flat layout is the union of <service>\scripts).
$pyPaths = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts')
$pathArgs = @(); foreach ($pp in $pyPaths) { $pathArgs += @('--paths', $pp) }
# t794u: the systray icon (assets\bob-systray.ico) is the exe's own icon (--icon) and is embedded as data so the worker
# window can show it too (bob_worker.set_console_icon).
$icoArgs = @()
$ico = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets\bob-systray.ico'
if ($ico -and (Test-Path -LiteralPath $ico)) { $icoArgs = @('--icon', $ico, '--add-data', "$ico;assets") }
else { Write-Host 'WARN bob-systray.ico not found - bob-worker.exe gets the default icon' }
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
$argList = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console', '--name', 'bob-worker',
    '--distpath', $dist, '--workpath', (Join-Path $work 'build'), '--specpath', $work)
$argList += $pathArgs
$argList += $icoArgs
$argList += @('--exclude-module', 'tkinter', '--exclude-module', 'numpy', '--exclude-module', 'pandas', '--exclude-module', 'matplotlib', $src)
# PyInstaller's isolated child can fail when PowerShell captures a live pipeline; use files for both streams.
$argText = (($argList | ForEach-Object {
        $v = [string]$_
        if ($v -match '[\s"]') { '"' + $v.Replace('"', '\"') + '"' } else { $v }
    }) -join ' ')
$logPath = Join-Path $work 'pyinstaller.stdout.log'
$errPath = Join-Path $work 'pyinstaller.stderr.log'
$proc = Start-Process -FilePath $Python -ArgumentList $argText -WorkingDirectory $RepoRoot -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput $logPath -RedirectStandardError $errPath
$code = $proc.ExitCode
$log = @()
if (Test-Path -LiteralPath $logPath) { $log += Get-Content -LiteralPath $logPath }
if (Test-Path -LiteralPath $errPath) { $log += Get-Content -LiteralPath $errPath }
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