#Requires -Version 5.1
<#
.SYNOPSIS
  Compile scripts\jeeves_main.py into jeeves.exe (PyInstaller, one file). FR #2301 / WP3 of #1993.
.DESCRIPTION
  Called by Pack-BobiverseRelease.ps1 for the Jeeves MSI. Target box needs neither Python nor PyInstaller.
  Smoke: jeeves.exe --self-test --check imports (exit 0/1/2 contract).
.OUTPUTS
  Full path of the built jeeves.exe.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Python = '',
    [switch]$SkipSmoke
)
$ErrorActionPreference = 'Stop'
$cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) {
    $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Bobiverse-Common.ps1'
}
. $cm
if (-not $RepoRoot) { $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot }
$src = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\jeeves_main.py'
if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }

$pyPaths = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts')
$pathArgs = @(); foreach ($pp in $pyPaths) { $pathArgs += @('--paths', $pp) }

# Monitor checks are imported as libraries by --self-test/--heal (WP2).
$monDir = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\tools\monitor'
if ($monDir -and (Test-Path -LiteralPath $monDir)) {
    $pathArgs += @('--paths', $monDir)
}

$hidden = @(
    'irc_agent', 'bobcallback', 'gitclaim', 'bobreport', 'intake', 'jeeves_locks', 'jeeves_maintenance', 'jeeves_checks', 'focus_ignore',
    'chair_commands', 'chair_health', 'chair_oper',
    'shop_chanserv', 'shop_listen', 'shop_ops',
    'health', 'queue_flow', 'focus_seat', 'webhook_health'
)
$hiddenArgs = @(); foreach ($h in $hidden) { $hiddenArgs += @('--hidden-import', $h) }

# FR #2522: bundle jeeves\checks (check_*.py plugins loaded by --self-test). Changes ship via PR + MRB + rebuild.
$checksDir = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\checks'
if ($checksDir -and (Test-Path -LiteralPath $checksDir)) {
    $hiddenArgs += @('--add-data', ('{0};checks' -f $checksDir))
}

if (-not $Python) {
    foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
        if ($c -and (Test-Path -LiteralPath $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw 'python.exe not found (needed to build jeeves.exe)' }
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $Python -m PyInstaller --version *> $null
$pyiOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $pyiOk) { throw "PyInstaller missing for $Python (pip install pyinstaller)" }

$work = Join-Path $OutDir 'jeeves-build'
if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$dist = Join-Path $work 'dist'
$argList = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console', '--name', 'jeeves',
    '--distpath', $dist, '--workpath', (Join-Path $work 'build'), '--specpath', $work)
$argList += $pathArgs
$argList += $hiddenArgs
$argList += @('--exclude-module', 'tkinter', '--exclude-module', 'numpy', '--exclude-module', 'pandas', '--exclude-module', 'matplotlib', $src)

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
$exe = Join-Path $dist 'jeeves.exe'
if ($code -ne 0 -or -not (Test-Path -LiteralPath $exe)) {
    ($log | Select-Object -Last 25) | ForEach-Object { Write-Host "  pyinstaller: $_" }
    throw "PyInstaller failed (exit $code)"
}

if (-not $SkipSmoke) {
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $probeHome = Join-Path $work 'smoke-home'
    New-Item -ItemType Directory -Force -Path $probeHome | Out-Null
    $probe = & $exe --self-test --check imports --home $probeHome --json 2>&1
    $pcode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($pcode -notin 0, 1) {
        throw "jeeves.exe smoke --self-test failed (exit $pcode): $($probe | Out-String)"
    }
    Write-Host ("INFO jeeves.exe smoke --self-test exit={0}" -f $pcode)
}

Write-Host ("INFO built {0} ({1:N1} MB)" -f $exe, ((Get-Item -LiteralPath $exe).Length / 1MB))
$exe
