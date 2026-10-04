#Requires -Version 5.1
<#
.SYNOPSIS
  Compile common/bob scripts\irc_agent.py into bob-ear.exe (PyInstaller, one file). Called by Pack-BobiverseRelease.ps1 for the bob MSI (FR #1481).
.DESCRIPTION
  Same toolchain as bob-worker.exe: Python + PyInstaller on the BUILD machine only; the target box runs the frozen
  exe without a system Python dependency for the ear process. Console subsystem so NSSM/Start-Bob can capture stdout.
.OUTPUTS
  The full path of the built bob-ear.exe.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) { $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Bobiverse-Common.ps1' }
. $cm
if (-not $RepoRoot) { $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot }
$src = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\irc_agent.py'
if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
$pyPaths = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts')
$pathArgs = @(); foreach ($pp in $pyPaths) { $pathArgs += @('--paths', $pp) }
$icoArgs = @()
$ico = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets\bob-systray.ico'
if ($ico -and (Test-Path -LiteralPath $ico)) { $icoArgs = @('--icon', $ico) }
else { Write-Host 'WARN bob-systray.ico not found - bob-ear.exe gets the default icon' }
if (-not $Python) {
    foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
        if ($c -and (Test-Path -LiteralPath $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw 'python.exe not found (needed to build bob-ear.exe)' }
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $Python -m PyInstaller --version *> $null
$pyiOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $pyiOk) { throw "PyInstaller missing for $Python (pip install pyinstaller)" }

$work = Join-Path $OutDir 'ear-build'
if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$dist = Join-Path $work 'dist'
$argList = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console', '--name', 'bob-ear',
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
$exe = Join-Path $dist 'bob-ear.exe'
if ($code -ne 0 -or -not (Test-Path -LiteralPath $exe)) {
    ($log | Select-Object -Last 25) | ForEach-Object { Write-Host "  pyinstaller: $_" }
    throw "PyInstaller failed (exit $code)"
}
# Smoke: frozen exe must parse argv (no IRC connect).
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$probe = & $exe --help 2>&1
$pcode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
$probeText = ($probe | Out-String)
if ($pcode -ne 0 -or ($probeText -notmatch 'nick' -and $probeText -notmatch '--host')) {
    throw "bob-ear.exe smoke test failed (exit $pcode): $probeText"
}
Write-Host ("INFO built {0} ({1:N1} MB)" -f $exe, ((Get-Item -LiteralPath $exe).Length / 1MB))
$exe
