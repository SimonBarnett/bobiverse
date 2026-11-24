#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Bob-{MachineId} ear (NSSM ircBob). Self-update check then bob-ear.exe (FR #1481) or irc_agent.py.
.NOTES
  Issue #3: use --channel (not --channels); load Ergo PASS from MSI config\ergo.password.
  Do not pass -Python via NSSM AppParameters (spaces break quoting) - resolve here.
  FR #1481: prefer scripts\bob-ear.exe (self-contained); fall back to python -u irc_agent.py for repo/dev trees.
  FR #7233: exe vs python is not chosen by file mtime; BOB_EAR_PYTHON=1 forces python.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$MachineId,
    [string]$BobHome = '',
    [string]$Python = '',
    [string]$InstallRoot = '',
    # Ergo host the ear connects to. Passed EXPLICITLY on the irc_agent command line (v0.1.20): a process whose
    # command line has no --host is indistinguishable from a stray agent to the tray/watch process matchers,
    # which killed the ear every ~30 s (ionos 06:32-06:51, the repeated "+h" grants). Install-Bob.ps1 bakes it.
    [string]$IrcHost = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'Bobiverse-Common.ps1')

$MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
$nick = "Bob-$MachineId"
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $scriptDir }
if (-not $BobHome) {
    # Prefer profile home when running as a real user; service-local home under LocalSystem (issue #3).
    if (Test-BobiverseIsLocalSystem) {
        $BobHome = Join-Path $InstallRoot 'home'
    } else {
        $BobHome = Join-Path $env:USERPROFILE '.bobiverse'
    }
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null

$env:BOB_MACHINE_ID = $MachineId
# Self-update on start: see the v0.1.17 block below (Update-BobiverseService.ps1).

# Ergo server PASS from config\ergo.password / home / env (public MSI no longer embeds - issue #4).
[void](Import-BobiverseErgoPassword -InstallRoot $InstallRoot -HomeDir $BobHome)
if (-not $env:BOB_IRC_PASSWORD) {
    Write-Host 'WARN BOB_IRC_PASSWORD unset - TLS to irc.ntsa.uk will fail without config\ergo.password'
}

# Issue #8: SASL as bob-{machine} so reserved Bob-* nicks get 001 (NickServ account owns the nick).
$nsFile = Join-Path $BobHome 'nickserv.password'
$env:BOB_IRC_SASL_USER = 'bob-' + $MachineId
if (Test-Path -LiteralPath $nsFile) {
    $env:BOB_IRC_SASL_PASSWORD = (Get-Content -LiteralPath $nsFile -Raw).Trim()
    $nsLen = $env:BOB_IRC_SASL_PASSWORD.Length
    Write-Host "INFO SASL user=$($env:BOB_IRC_SASL_USER) from $nsFile (len=$nsLen)"
} else {
    Write-Host "WARN missing $nsFile - reserved nick will fail without BOB_IRC_SASL_PASSWORD"
}

# t781u/t782u start-up update order (dev path first, release path second):
#   1. repo fast-forward: <InstallRoot> is a sparse git work tree (bob + common) -> fetch + ff-only origin/main, flat runtime files
#      recomposed from it (Sync-BobiverseFromRepo.ps1). Never destroys local edits/commits. FR #9508: out-of-process with
#      BOB_START_SYNC_TIMEOUT_SEC (default 90s) so a hung git fetch cannot block bob-ear under nssm. Falls back to the
#      installed version on any failure/timeout. BOBIVERSE_REPO (explicit dev override) syncs from that clone instead.
#   2. release self-update (Update-BobiverseService.ps1): only when a GitHub release is newer than the VERSION now installed (the
#      ff'd tree counts), so the MSI path stays the safety net for boxes where git is unavailable.
#   Opt out of BOTH with BOBIVERSE_NO_UPDATE=1 (FR #6259: trim Process+Machine via Get-BobiverseNoUpdateReason;
#   suppress Sync AND Update invocation before either begins). Release-only opt out: BOB_AUTOUPDATE=0.
$noUpdateReason = Get-BobiverseNoUpdateReason -InstallRoot $InstallRoot
if ($noUpdateReason) {
    Write-Host ("INFO no-update-guard seen=1 effective=1 reason={0} sync=suppressed updater=suppressed" -f $noUpdateReason)
} else {
    Write-Host "INFO no-update-guard seen=0 effective=0 sync=allowed updater=allowed"
    # FR #9508: never call Sync/Update in-process under nssm. A hung git fetch left
    # Start-Bob with zero children while Status=Running (marchhare #9496 class).
    # Out-of-process + WaitForExit + taskkill /T (same spirit as FR #9350/#9435 monitor).
    $syncTimeoutSec = 90
    if ($env:BOB_START_SYNC_TIMEOUT_SEC -match '^\d+$') {
        $syncTimeoutSec = [int]$env:BOB_START_SYNC_TIMEOUT_SEC
    }
    if ($syncTimeoutSec -lt 15) { $syncTimeoutSec = 15 }
    if ($syncTimeoutSec -gt 300) { $syncTimeoutSec = 300 }
    $psExe = (Get-Command powershell.exe -ErrorAction Stop).Source
    function Invoke-BobStartTimedScript {
        param(
            [Parameter(Mandatory)][string]$Label,
            [Parameter(Mandatory)][string]$FilePath,
            [Parameter(Mandatory)][string[]]$ArgumentList
        )
        if (-not (Test-Path -LiteralPath $FilePath)) { return }
        $outLog = Join-Path $env:TEMP ("bob-start-{0}-{1}.out.log" -f $Label, $PID)
        $errLog = Join-Path $env:TEMP ("bob-start-{0}-{1}.err.log" -f $Label, $PID)
        $argList = @(
            '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', $FilePath
        ) + $ArgumentList
        $p = $null
        try {
            $p = Start-Process -FilePath $psExe -ArgumentList $argList `
                -PassThru -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog
            $ms = [Math]::Max(5000, $syncTimeoutSec * 1000)
            if (-not $p.WaitForExit($ms)) {
                try {
                    if (-not $p.HasExited) {
                        Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" `
                            -ArgumentList @('/PID', [string]$p.Id, '/T', '/F') `
                            -Wait -WindowStyle Hidden | Out-Null
                    }
                } catch {
                    try { if (-not $p.HasExited) { $p.Kill() } } catch { }
                }
                Write-Host ("WARN FR #9508 {0} timeout after {1}s; proceeding to bob-ear" -f $Label, $syncTimeoutSec)
            } elseif ($p.ExitCode -ne 0) {
                Write-Host ("WARN FR #9508 {0} exit={1}; proceeding to bob-ear" -f $Label, $p.ExitCode)
            }
        } catch {
            Write-Host ("WARN FR #9508 {0}: {1}" -f $Label, $_.Exception.Message)
        } finally {
            if ($p) { try { $p.Dispose() } catch { } }
        }
    }
    $sync = Join-Path $scriptDir 'Sync-BobiverseFromRepo.ps1'
    Invoke-BobStartTimedScript -Label 'sync-from-repo' -FilePath $sync `
        -ArgumentList @('-Product', 'bob', '-InstallRoot', $InstallRoot)
    # v0.1.17 self-update on service start: token-less GitHub latest-release check; when newer, a DETACHED
    # helper (scheduled task) downloads + sha256-verifies the MSI, replaces the install and rolls back on failure.
    # Never blocks or fails the start. Never touches Ergo. Opt out: BOB_AUTOUPDATE=0 (or BOBIVERSE_NO_UPDATE=1).
    $updater = Join-Path $scriptDir 'Update-BobiverseService.ps1'
    Invoke-BobStartTimedScript -Label 'self-update' -FilePath $updater `
        -ArgumentList @('-Product', 'bob', '-InstallRoot', $InstallRoot, '-ServiceName', 'ircBob')
}

# FR #1481 / MRB #1488: prefer bob-ear.exe *after* sync/self-update so a just-staged exe is seen.
# FR #7233: never compare bob-ear.exe vs bobreport.py mtimes (CI overlay can leave the
# installed exe older). Frozen ears still load install scripts via prefer_install_scripts_path
# (FR #6237). Dev/hotpatch python path: BOB_EAR_PYTHON=1.
. (Join-Path $scriptDir 'Select-BobEarLaunch.ps1')
$earPick = Select-BobEarLaunch -ScriptDir $scriptDir -InstallRoot $InstallRoot
$earExe = Join-Path $scriptDir 'bob-ear.exe'
$useEarExe = [bool]$earPick.UseExe
$agent = Join-Path $scriptDir 'irc_agent.py'
$shop = "#$MachineId"
# FR #3834: Bob ears also JOIN #wonderland (airc client fallback; Jeeves grants +o).
$channel = "#bobiverse,#wonderland,$shop"
if (-not $IrcHost) { $IrcHost = [string]$env:BOB_IRC_HOST }
if (-not $IrcHost) { $IrcHost = 'irc.ntsa.uk' }
$IrcHost = $IrcHost.Trim()
if ($IrcHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') { throw "invalid -IrcHost '$IrcHost'" }
# FR #2666: frozen bob-ear.exe resolves __file__ under _MEIPASS (often C:\Windows\Temp).
# Export BOB_INSTALL_ROOT so startworker queue_dir sees InstallRoot\run\startworker (tray.alive)
# even on an older bob-ear.exe that lacks --install-root / frozen-aware resolve. Do not pass
# --install-root here until every live ear accepts that flag (unknown argv aborts start).
$env:BOB_INSTALL_ROOT = $InstallRoot
$earArgs = @('--nick', $nick, '--home', $BobHome, '--channel', $channel, '--host', $IrcHost)
if ($useEarExe) {
    # FR #7390: log Select-BobEarLaunch.ps1 hash next to exe sha256 / source=.
    $launcherSha = ''
    try {
        $selPath = Join-Path $scriptDir 'Select-BobEarLaunch.ps1'
        if (Test-Path -LiteralPath $selPath -PathType Leaf) {
            $launcherSha = [string](Get-FileHash -LiteralPath $selPath -Algorithm SHA256).Hash
        }
    } catch { }
    Write-Host ("INFO ear host={0} nick={1} channels={2} via=bob-ear.exe sha256={3} launcher_sha256={4} source={5} version={6} (FR #1481/#7233/#7390)" -f `
        $IrcHost, $nick, $channel, $earPick.Sha256, $(if ([string]::IsNullOrWhiteSpace($launcherSha)) { 'unknown' } else { $launcherSha }), $(if ([string]::IsNullOrWhiteSpace([string]$earPick.SourceCommit)) { 'unknown' } else { $earPick.SourceCommit }), $earPick.ProductVersion)
    & $earExe @earArgs
    exit $LASTEXITCODE
}
if (-not $Python) {
    try { $Python = Resolve-BobiversePython } catch { throw 'python.exe missing (and scripts\bob-ear.exe not present; FR #1481)' }
}
if (-not (Test-Path -LiteralPath $agent)) { throw "missing $agent (and bob-ear.exe not present)" }
Write-Host "INFO ear host=$IrcHost nick=$nick channels=$channel via=python irc_agent.py"
& $Python -u $agent @earArgs
exit $LASTEXITCODE
