#Requires -Version 5.1
<#
.SYNOPSIS
  Start a NEW Jeeves maintenance agent (FR #2412) after --heal still failing.
.DESCRIPTION
  Shared launcher used by jeeves_maintenance / operators. Same fuel pick as tray Agent
  via bob-worker.exe --mode maintenance. CWD is <drive>:\ai\jeeves (or -InstallRoot).
  Never resumes. Files diagnosis via intake (agent prompt).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$BobInstallRoot = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not $InstallRoot) {
    $cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (-not (Test-Path -LiteralPath $cm)) {
        $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Bobiverse-Common.ps1'
    }
    if (Test-Path -LiteralPath $cm) {
        . $cm
        $InstallRoot = Join-Path (Get-BobiverseAiRoot) 'jeeves'
    } else {
        $InstallRoot = Split-Path -Parent $PSScriptRoot
    }
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'AGENTS.md'))) {
    Write-Error "Jeeves install root missing AGENTS.md: $InstallRoot"
    exit 2
}
if (-not $BobInstallRoot) {
    $ai = Split-Path -Parent $InstallRoot
    $BobInstallRoot = Join-Path $ai 'bob'
}
$BobInstallRoot = [IO.Path]::GetFullPath($BobInstallRoot)
$exe = Join-Path $BobInstallRoot 'worker\bob-worker.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "bob-worker.exe missing at $exe (install/upgrade the bob MSI)."
    exit 2
}
$binDir = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
$run = Join-Path $binDir ("bob-worker-{0}.exe" -f $hash)
if (-not (Test-Path -LiteralPath $run)) {
    Copy-Item -LiteralPath $exe -Destination $run -Force
}
$argv = @('--mode', 'maintenance', '--install-root', $BobInstallRoot, '--work-root', $InstallRoot)
if ($DryRun) {
    $argv += '--dry-run'
    & $run @argv
    exit $LASTEXITCODE
}
Write-Host "INFO Start-JeevesMaintenance cwd=$InstallRoot (FR #2412)"
Start-Process -FilePath $run -ArgumentList $argv -WorkingDirectory $InstallRoot
exit 0
