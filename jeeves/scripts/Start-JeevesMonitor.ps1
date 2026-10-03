<#
.SYNOPSIS
  Start a NEW Jeeves MONITORING agent (FR #787 Start Menu 'Start Jeeves Monitor').
.DESCRIPTION
  Same fuel selection as the Bob Fleet systray Agent item (cursor > grok > key prompt)
  via bob-worker.exe --mode monitor. CWD is this Jeeves install root. Never resumes.
  Looks for bob-worker.exe under sibling <ai root>\bob\worker (or -BobInstallRoot).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$BobInstallRoot = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
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
    Write-Error "bob-worker.exe missing at $exe (install/upgrade the bob MSI). Jeeves Monitor uses the same agent launcher as the tray Agent item."
    exit 2
}
# t765u-style: run a LocalAppData copy so upgrades are not blocked
$binDir = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
$run = Join-Path $binDir ("bob-worker-{0}.exe" -f $hash)
if (-not (Test-Path -LiteralPath $run)) {
    Copy-Item -LiteralPath $exe -Destination $run -Force
}
$argv = @('--mode', 'monitor', '--install-root', $BobInstallRoot, '--work-root', $InstallRoot)
if ($DryRun) {
    $argv += '--dry-run'
    & $run @argv
    exit $LASTEXITCODE
}
# Visible console = the ONE agent window (same as tray Agent)
Start-Process -FilePath $run -ArgumentList $argv -WorkingDirectory $InstallRoot
exit 0
