<#
.SYNOPSIS
  Start a NEW Jeeves MONITORING agent (FR #787 / #954 Start Menu 'Start Jeeves Monitor').
.DESCRIPTION
  Same fuel selection as the Bob Fleet systray Agent item (cursor > grok > key prompt)
  via bob-worker.exe --mode monitor. CWD is this Jeeves install root. Never resumes.
  The monitor_prompt tells the agent to read AGENTS.md and run the monitor-start skill
  immediately (do not wait for Simon). Looks for bob-worker.exe under sibling
  <ai root>\bob\worker (or -BobInstallRoot).

  FR #8577: Drive-root InstallRoot (J: or J:\) is supported. Split-Path -Parent of a
  drive root is empty; do not Join-Path that into bob. Fall back to
  <SystemDrive>\ai\bob, C:\ai\bob, D:\ai\bob when worker\bob-worker.exe exists, else
  require -BobInstallRoot.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$BobInstallRoot = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

function Normalize-JeevesRoot([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $p }
    $p = $p.Trim().Trim('"')
    # CMD quoting of "J:\" can eat the close-quote; callers may pass J: or J:\.
    if ($p -match '^[A-Za-z]:$') { $p = $p + '\' }
    try {
        return [IO.Path]::GetFullPath($p)
    } catch {
        if ($p -match '^[A-Za-z]:\\?$') {
            return ($p.Substring(0, 2) + '\')
        }
        throw
    }
}

function Resolve-BobInstallRootFromJeeves([string]$JeevesRoot) {
    $ai = Split-Path -Parent $JeevesRoot
    if (-not [string]::IsNullOrWhiteSpace($ai) -and $ai -ne $JeevesRoot) {
        $sib = Join-Path $ai 'bob'
        if (Test-Path -LiteralPath (Join-Path $sib 'worker\bob-worker.exe')) {
            return $sib
        }
        # Sibling path may exist without exe yet; still prefer conventional layout.
        if (Test-Path -LiteralPath $sib) { return $sib }
    }
    $sys = if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' }
    foreach ($cand in @((Join-Path $sys 'ai\bob'), 'C:\ai\bob', 'D:\ai\bob')) {
        if (Test-Path -LiteralPath (Join-Path $cand 'worker\bob-worker.exe')) {
            return $cand
        }
    }
    return ''
}

if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
$InstallRoot = Normalize-JeevesRoot $InstallRoot
if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'AGENTS.md'))) {
    Write-Error "Jeeves install root missing AGENTS.md: $InstallRoot"
    exit 2
}
if (-not $BobInstallRoot) {
    $BobInstallRoot = Resolve-BobInstallRootFromJeeves $InstallRoot
    if (-not $BobInstallRoot) {
        Write-Error "Jeeves InstallRoot is a drive root ($InstallRoot) with no sibling bob\, or bob-worker.exe was not found under C:\ai\bob / D:\ai\bob. Pass -BobInstallRoot (e.g. C:\ai\bob)."
        exit 2
    }
}
$BobInstallRoot = Normalize-JeevesRoot $BobInstallRoot
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
