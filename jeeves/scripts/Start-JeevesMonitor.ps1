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
# FR #8860: non-chair composed installs (drive-root J:\) never run Start-Jeeves,
# so tools\monitor lagged main after #8585. Refresh from tip when the flat
# Sync script is beside this file. A repo tree without that sibling is a no-op.
$syncMon = Join-Path $PSScriptRoot 'Sync-BobiverseFromRepo.ps1'
if (Test-Path -LiteralPath $syncMon) {
    try {
        if ($DryRun) {
            & $syncMon -Product jeeves -InstallRoot $InstallRoot -DryRun
        } else {
            & $syncMon -Product jeeves -InstallRoot $InstallRoot
        }
        # FR #9100: warn when Sync fails; do not block monitor startup.
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            Write-Warning ("FR #9100 sync-monitor exit={0}; tools/monitor may be stale" -f $LASTEXITCODE)
        }
    } catch {
        Write-Warning ("FR #8860 sync-monitor: {0}" -f $_.Exception.Message)
    }
}
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
# FR #8579: warn when this host has no local chair queue (monitor still starts;
# health/queue/stale_digest soft-pass via live /bob/v1/report when fresh).
$chairProbe = Join-Path $env:USERPROFILE '.jeeves\queue.json'
if (-not (Test-Path -LiteralPath $chairProbe)) {
    Write-Warning "FR #8579: no local chair queue at $chairProbe - this looks like a non-chair host. Monitor checks soft-pass local chair probes when live https://irc.ntsa.uk/bob/v1/report is fresh; prefer running monitor on the ionos chair for local service truth."
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
