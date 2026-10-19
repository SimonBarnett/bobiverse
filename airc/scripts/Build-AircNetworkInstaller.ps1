#Requires -Version 5.1
<#
.SYNOPSIS
  Compile airc_network_installer into airc-network-installer.exe (PyInstaller, one file, UAC admin). FR #3991.
.DESCRIPTION
  Called by Pack-BobiverseRelease.ps1 for the Airc MSI + release asset. Uses --uac-admin so the
  exe requests elevation (requireAdministrator). Smoke: --selftest then --help (exit 0).
  PsExec is NOT bundled (Sysinternals licence).
.OUTPUTS
  Full path of the built airc-network-installer.exe.
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
$src = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\airc_network_installer_main.py'
if (-not (Test-Path -LiteralPath $src)) { throw "missing $src" }
$pkg = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\airc_network_installer'
if (-not (Test-Path -LiteralPath $pkg)) { throw "missing package $pkg" }

$pyPaths = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts')
$pathArgs = @(); foreach ($pp in $pyPaths) { $pathArgs += @('--paths', $pp) }

$hidden = @(
    'airc_network_installer',
    'airc_network_installer.cli',
    'airc_network_installer.core',
    'airc_network_installer.github_msi',
    'airc_network_installer.install'
)
$hiddenArgs = @(); foreach ($h in $hidden) { $hiddenArgs += @('--hidden-import', $h) }

if (-not $Python) {
    foreach ($c in @((Get-Command python.exe -ErrorAction SilentlyContinue).Source, 'C:\Program Files\Python312\python.exe', 'C:\Python312\python.exe')) {
        if ($c -and (Test-Path -LiteralPath $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw 'python.exe not found (needed to build airc-network-installer.exe)' }
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $Python -m PyInstaller --version *> $null
$pyiOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $pyiOk) { throw "PyInstaller missing for $Python (pip install pyinstaller)" }

$work = Join-Path $OutDir 'airc-network-installer-build'
if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$dist = Join-Path $work 'dist'
# FR #3991: --uac-admin embeds requireAdministrator so elevation is requested on launch.
$argList = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
    '--uac-admin',
    '--name', 'airc-network-installer',
    '--distpath', $dist,
    '--workpath', (Join-Path $work 'build'),
    '--specpath', $work
)
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
$exe = Join-Path $dist 'airc-network-installer.exe'
if ($code -ne 0 -or -not (Test-Path -LiteralPath $exe)) {
    ($log | Select-Object -Last 25) | ForEach-Object { Write-Host "  pyinstaller: $_" }
    throw "PyInstaller failed (exit $code)"
}

if (-not $SkipSmoke) {
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $probe = & $exe --selftest 2>&1
    $pcode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($pcode -ne 0) {
        throw "airc-network-installer.exe smoke --selftest failed (exit $pcode): $($probe | Out-String)"
    }
    Write-Host ("INFO airc-network-installer.exe smoke --selftest exit={0}" -f $pcode)
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $help = & $exe --help 2>&1
    $hcode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    $helpText = ($help | Out-String)
    if ($hcode -ne 0 -or ($helpText -notmatch 'profile' -and $helpText -notmatch 'selftest')) {
        throw "airc-network-installer.exe smoke --help failed (exit $hcode): $helpText"
    }
    Write-Host 'INFO airc-network-installer.exe smoke --help ok'
}

Write-Host ("INFO built {0} ({1:N1} MB)" -f $exe, ((Get-Item -LiteralPath $exe).Length / 1MB))
$exe
