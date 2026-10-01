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

# Fast-forward C:\ai\bobiverse (or BOBIVERSE_REPO) and sync into this install tree.
# Operators may set BOBIVERSE_NO_UPDATE=1 to skip. LocalSystem is allowed to update.
# v0.1.17 self-update on service start: token-less GitHub latest-release check; when newer, a DETACHED
# helper (scheduled task) downloads + sha256-verifies the MSI, replaces the install and rolls back on failure.
# Never blocks or fails the start. Never touches Ergo. Opt out: BOB_AUTOUPDATE=0 (or BOBIVERSE_NO_UPDATE=1).
# BOBIVERSE_REPO (explicit dev opt-in) still fast-forwards that clone into this tree.
$updater = Join-Path $scriptDir 'Update-BobiverseService.ps1'
if (Test-Path -LiteralPath $updater) {
    try { & $updater -Product jeeves -InstallRoot $RepoRoot -ServiceName ircJeeves }
    catch { Write-Host "WARN self-update: $($_.Exception.Message)" }
}
$sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
if ($env:BOBIVERSE_REPO -and (Test-Path -LiteralPath $sync) -and ($env:BOBIVERSE_NO_UPDATE -ne '1')) {
    try { & $sync -Product jeeves -InstallRoot $RepoRoot }
    catch { Write-Host "WARN sync-from-repo: $($_.Exception.Message)" }
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
function Test-BobCallbackListening {
    try {
        $conns = Get-NetTCPConnection -LocalPort 7700 -State Listen -ErrorAction SilentlyContinue
        return [bool]$conns
    } catch {
        return $false
    }
}
$callback = Join-Path $scriptDir 'bobcallback.py'
if ((Test-Path -LiteralPath $callback) -and -not (Test-BobCallbackListening)) {
    Write-Host 'INFO starting bobcallback on 127.0.0.1:7700'
    $cbArgs = @(
        '-u', $callback,
        '--home', $env:BOB_DIGEST_HOME,
        '--bind', '127.0.0.1',
        '--port', '7700'
    )
    try {
        Start-Process -FilePath $Python -ArgumentList $cbArgs -WorkingDirectory $scriptDir -WindowStyle Hidden | Out-Null
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "WARN bobcallback start failed: $($_.Exception.Message)"
    }
}

$watchWh = Join-Path $scriptDir 'Watch-BobWebhooks.ps1'
if (Test-Path -LiteralPath $watchWh) {
    try { & $watchWh -DigestHome $env:BOB_DIGEST_HOME } catch {
        Write-Host "WARN Watch-BobWebhooks: $($_.Exception.Message)"
    }
}

& $Python -u $agent --chair --nick Jeeves --home $ChairHome
exit $LASTEXITCODE
