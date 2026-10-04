#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Jeeves chair (used by NSSM ircJeeves). Runs MSI self-update check first.
#>
[CmdletBinding()]
param(
    [string]$ChairHome = '',
    [string]$Python = '',
    [string]$RepoRoot = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'Bobiverse-Common.ps1')
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $scriptDir }
if (-not $ChairHome) {
    if (Test-BobiverseIsLocalSystem) {
        $ChairHome = Join-Path $RepoRoot 'home-jeeves'
    } else {
        $ChairHome = Join-Path $env:USERPROFILE '.jeeves'
    }
}
New-Item -ItemType Directory -Force -Path $ChairHome | Out-Null
if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing' }
}
# #53: everything the chair + webhooks need lives under THIS install (config\) and the
# jeeves/bobiverse homes; BOB_* variables only (legacy names are not read).
$env:BOB_CONFIG_DIR = if ($env:BOB_CONFIG_DIR) { $env:BOB_CONFIG_DIR } else { Join-Path $RepoRoot 'config' }
$env:BOB_HOME = $ChairHome

[void](Import-BobiverseErgoPassword -InstallRoot $RepoRoot -HomeDir $ChairHome)

# t781u/t782u start-up update order (dev path first, release path second):
#   1. repo fast-forward: <InstallRoot> is a sparse git work tree (jeeves + common) -> fetch + ff-only origin/main, flat runtime files
#      recomposed from it (Sync-BobiverseFromRepo.ps1). Never destroys local edits/commits, never blocks the start, falls back to the
#      installed version on any failure. BOBIVERSE_REPO (explicit dev override) syncs from that clone instead.
#   2. release self-update (Update-BobiverseService.ps1): only when a GitHub release is newer than the VERSION now installed (the
#      ff'd tree counts), so the MSI path stays the safety net for boxes where git is unavailable.
#   Opt out of BOTH with BOBIVERSE_NO_UPDATE=1; of the release check only with BOB_AUTOUPDATE=0.
$sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
if ((Test-Path -LiteralPath $sync) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try { & $sync -Product jeeves -InstallRoot $RepoRoot }
    catch { Write-Host "WARN sync-from-repo: $($_.Exception.Message)" }
}
# LocalSystem is allowed to update.
# v0.1.17 self-update on service start: token-less GitHub latest-release check; when newer, a DETACHED
# helper (scheduled task) downloads + sha256-verifies the MSI, replaces the install and rolls back on failure.
# Never blocks or fails the start. Never touches Ergo. Opt out: BOB_AUTOUPDATE=0 (or BOBIVERSE_NO_UPDATE=1).
$updater = Join-Path $scriptDir 'Update-BobiverseService.ps1'
if (Test-Path -LiteralPath $updater) {
    try { & $updater -Product jeeves -InstallRoot $RepoRoot -ServiceName ircJeeves }
    catch { Write-Host "WARN self-update: $($_.Exception.Message)" }
}

$agent = Join-Path $scriptDir 'irc_agent.py'
if (-not (Test-Path -LiteralPath $agent)) { throw "missing $agent" }

$env:BOB_DIGEST_HOME = if ($env:BOB_DIGEST_HOME) { $env:BOB_DIGEST_HOME } else {
    if (Test-BobiverseIsLocalSystem) { Join-Path $RepoRoot 'home' } else { Join-Path $env:USERPROFILE '.bobiverse' }
}
New-Item -ItemType Directory -Force -Path $env:BOB_DIGEST_HOME | Out-Null
# First start after upgrade: copy data from the old ~\.agentic-irc-* homes (kept as backup).
$homeMigrate = Join-Path $scriptDir 'bob_home.py'
if (Test-Path -LiteralPath $homeMigrate) {
    try { & $Python $homeMigrate migrate --chair-home $ChairHome --digest-home $env:BOB_DIGEST_HOME --config-dir $env:BOB_CONFIG_DIR } catch {
        Write-Host "WARN home migration: $($_.Exception.Message)"
    }
}

# Ensure BobIrcd is up before chair (monitor path; !recycle jeeves still chair-only).
$watchIrcd = Join-Path $scriptDir 'Watch-BobIrcd.ps1'
if (Test-Path -LiteralPath $watchIrcd) {
    try { & $watchIrcd -DigestHome $env:BOB_DIGEST_HOME } catch {
        Write-Host "WARN Watch-BobIrcd: $($_.Exception.Message)"
    }
}

# Ensure bobcallback listens on 127.0.0.1:7700 (digest + intake + jira).
# FR #1014: ARR on irc.ntsa.uk returns IIS 502.3 when nothing listens on :7700.
function Test-BobCallbackListening {
    try {
        $conns = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue
        return [bool]$conns
    } catch {
        return $false
    }
}
function Wait-BobCallbackListening {
    param([int]$TimeoutSec = 20)
    $deadline = [datetime]::UtcNow.AddSeconds([math]::Max(1, $TimeoutSec))
    while ([datetime]::UtcNow -lt $deadline) {
        if (Test-BobCallbackListening) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return (Test-BobCallbackListening)
}
$callback = Join-Path $scriptDir 'bobcallback.py'
# FR #1472 / #1455: user-context starts prefer the supervised restart wrapper (same as Register fallback).
function Start-BobCallbackUserContext {
    param(
        [string]$PythonExe,
        [string]$CallbackPy,
        [string]$WorkDir,
        [string]$DigestHome
    )
    $supervise = Join-Path $WorkDir 'Start-BobCallbackSupervised.ps1'
    if (-not (Test-Path -LiteralPath $supervise)) {
        $supervise = Join-Path (Split-Path -Parent $CallbackPy) 'Start-BobCallbackSupervised.ps1'
    }
    if (Test-Path -LiteralPath $supervise) {
        $fbArgs = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $supervise,
            '-Python', $PythonExe, '-ScriptPath', $CallbackPy,
            '-DigestHome', $DigestHome, '-Port', '7700'
        )
        Start-Process -FilePath 'powershell.exe' -ArgumentList $fbArgs -WorkingDirectory $WorkDir -WindowStyle Hidden | Out-Null
        Write-Host 'INFO bobcallback via Start-BobCallbackSupervised.ps1 (FR #1472)'
        return $true
    }
    $cbArgs = @(
        '-u', $CallbackPy,
        '--home', $DigestHome,
        '--bind', '127.0.0.1',
        '--port', '7700'
    )
    Start-Process -FilePath $PythonExe -ArgumentList $cbArgs -WorkingDirectory $WorkDir -WindowStyle Hidden | Out-Null
    Write-Host 'WARN Start-BobCallbackSupervised.ps1 missing; bare python bobcallback (FR #1472)'
    return $true
}
if ((Test-Path -LiteralPath $callback) -and -not (Test-BobCallbackListening)) {
    Write-Host 'INFO starting bobcallback on 127.0.0.1:7700'
    $started = $false
    # Prefer the durable scheduled task when present (survives service recycle better than a naked Start-Process).
    $cbTask = Get-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue
    if ($cbTask) {
        try {
            if ($cbTask.State -eq 'Running') {
                Stop-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
            Start-ScheduledTask -TaskName 'BobCallback'
            $started = $true
            Write-Host 'INFO bobcallback via scheduled task BobCallback'
        } catch {
            Write-Host "WARN BobCallback task start failed: $($_.Exception.Message)"
        }
    }
    if (-not $started) {
        try {
            Start-BobCallbackUserContext -PythonExe $Python -CallbackPy $callback -WorkDir $scriptDir -DigestHome $env:BOB_DIGEST_HOME | Out-Null
            $started = $true
        } catch {
            Write-Host "WARN bobcallback start failed: $($_.Exception.Message)"
        }
    }
    if ($started) {
        if (Wait-BobCallbackListening -TimeoutSec 20) {
            Write-Host 'INFO bobcallback listening on 127.0.0.1:7700'
        } else {
            # FR #1316: task Running but no LISTENING after 15–20s = wedge (SYSTEM vs Admin home).
            Write-Host 'WARN bobcallback not listening on 127.0.0.1:7700 after start (ARR intake will 502.3)'
            if ($cbTask) {
                Write-Host 'WARN BobCallback wedge: stopping task and falling back to supervised user-context (FR #1472)'
                try { Stop-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue } catch { }
                Start-Sleep -Seconds 1
                try {
                    Start-BobCallbackUserContext -PythonExe $Python -CallbackPy $callback -WorkDir $scriptDir -DigestHome $env:BOB_DIGEST_HOME | Out-Null
                    if (Wait-BobCallbackListening -TimeoutSec 15) {
                        Write-Host 'INFO bobcallback listening via supervised user-context fallback (FR #1316/#1472)'
                    }
                } catch {
                    Write-Host "WARN user-context bobcallback fallback failed: $($_.Exception.Message)"
                }
            }
        }
    }
}

# FR #1316 monitor: task claims Running but nothing listens after 15s → treat as wedge.
$cbTaskState = Get-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue
if ($cbTaskState -and $cbTaskState.State -eq 'Running' -and -not (Test-BobCallbackListening)) {
    Write-Host 'WARN BobCallback task Running but :7700 not LISTENING — wedge (FR #1316)'
}

$watchWh = Join-Path $scriptDir 'Watch-BobWebhooks.ps1'
if (Test-Path -LiteralPath $watchWh) {
    try { & $watchWh -DigestHome $env:BOB_DIGEST_HOME } catch {
        Write-Host "WARN Watch-BobWebhooks: $($_.Exception.Message)"
    }
}

& $Python -u $agent --chair --nick Jeeves --home $ChairHome
exit $LASTEXITCODE
