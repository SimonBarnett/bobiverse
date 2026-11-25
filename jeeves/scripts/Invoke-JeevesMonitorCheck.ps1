<#
.SYNOPSIS
  Token-free Jeeves MONITORING check runner (FR #787).
.DESCRIPTION
  Runs one named check under tools\monitor\*.py. Exit 0=ok, 1=finding, 2=error.
  Prints one JSON line on stdout. Prefer these scripts over reasoning.
.PARAMETER Check
  health | idle_seats | queue_flow | stale_digest | workers_last_good_orphan | online_zero_workers | giveup_loops | stuck_accepted | auto_feed | auto_focus | focus_present | focus_redundant_items | seats_stuck_doing | opencode_seats | skill_promote_backlog | intake_allowlist | ticket_closure | open_pr_stale_base | open_pr_mrb_missing | needs_human_false_positive | depends_on | fr_digest | github_rate_limit | pr_hold_labels | wake_brief | wake_grok_bot_bob | ircbob_ear | walrus_jeeves_install_ready | redqueen_bob_tray_install_ready | intervene_assign | shop_wire_assign | mrb_same_machine_starve | models_put_forward | disk_starvation | webhooks_up_with_chair | chair_progress | digest_ci_gate | lessons_digest_harvest | 9830_harvest
.PARAMETER DryRun
  Offline: scripts emit ok JSON and exit 0.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('health','idle_seats','queue_flow','stale_digest','workers_last_good_orphan','online_zero_workers','giveup_loops','stuck_accepted','auto_feed','auto_focus','focus_present','focus_redundant_items','seats_stuck_doing','opencode_seats','skill_promote_backlog','intake_allowlist','github_resync_focus','ticket_closure','open_pr_stale_base','open_pr_mrb_missing','needs_human_false_positive','depends_on','fr_digest','github_rate_limit','pr_hold_labels','wake_brief','wake_grok_bot_bob','ircbob_ear','walrus_jeeves_install_ready','redqueen_bob_tray_install_ready','intervene_assign','shop_wire_assign','mrb_same_machine_starve','models_put_forward','disk_starvation','webhooks_up_with_chair','chair_progress','digest_ci_gate','lessons_digest_harvest','9830_harvest')]
    [string]$Check,
    [switch]$DryRun,
    [string]$InstallRoot = '',
    [string]$ChairHome = '',
    [string]$DigestHome = '',
    # FR #9350: bound live Sync so a hung worktree fetch cannot block tools\monitor checks.
    [int]$SyncTimeoutSec = 25,
    # FR #9350: at-most-once Sync per interval (per InstallRoot stamp); 0 disables throttle.
    [int]$SyncMinIntervalSec = 300,
    # FR #9435: skip Sync entirely (env BOB_MONITOR_SKIP_SYNC=1 also). Prefer when tip-fresh.
    [switch]$SkipSync
)
$ErrorActionPreference = 'Stop'
$here = if ($InstallRoot) { $InstallRoot } else { Split-Path -Parent $PSScriptRoot }
# FR #9007 / FR #9309: refresh tools\monitor before the check when Sync is resolvable.
# Drive-root J:\ has empty Split-Path -Parent; resolve bob like Start-JeevesMonitor.
# FR #9309: prefer a tip Sync that contains sync-monitor-force over a stale flat J:\scripts copy.
$syncName = 'Sync-BobiverseFromRepo.ps1'
function Resolve-BobInstallRootFromJeeves([string]$JeevesRoot) {
    $ai = Split-Path -Parent $JeevesRoot
    if (-not [string]::IsNullOrWhiteSpace($ai) -and $ai -ne $JeevesRoot) {
        $sib = Join-Path $ai 'bob'
        if (Test-Path -LiteralPath (Join-Path $sib 'worker\bob-worker.exe')) { return $sib }
        if (Test-Path -LiteralPath $sib) { return $sib }
    }
    $sys = if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' }
    foreach ($cand in @((Join-Path $sys 'ai\bob'), 'C:\ai\bob', 'D:\ai\bob')) {
        if (Test-Path -LiteralPath (Join-Path $cand 'worker\bob-worker.exe')) { return $cand }
    }
    return ''
}
$bobRoot = Resolve-BobInstallRootFromJeeves $here
if (-not $bobRoot) {
    $parent = Split-Path -Parent $here
    if ($parent -and $parent -ne $here) { $bobRoot = $parent }
}
$syncCands = @()
if ($bobRoot) {
    $syncCands += (Join-Path $bobRoot ('common\scripts\' + $syncName))
    $syncCands += (Join-Path $bobRoot ('scripts\' + $syncName))
}
$syncCands += @(
    (Join-Path $PSScriptRoot $syncName),
    (Join-Path $here ('scripts\' + $syncName))
)
$syncMon = ''
$syncFallback = ''
foreach ($c in $syncCands) {
    if (-not ($c -and (Test-Path -LiteralPath $c))) { continue }
    $hit = $false
    try {
        foreach ($line in [IO.File]::ReadLines($c)) {
            if ($line -match 'sync-monitor-force') { $hit = $true; break }
        }
    } catch { }
    if ($hit) { $syncMon = $c; break }
    if (-not $syncFallback) { $syncFallback = $c }
}
if (-not $syncMon) { $syncMon = $syncFallback }
# Env overrides (scheduled hosts may pin without editing the wrapper).
if ($env:BOB_MONITOR_SYNC_TIMEOUT_SEC -match '^\d+$') {
    $SyncTimeoutSec = [int]$env:BOB_MONITOR_SYNC_TIMEOUT_SEC
}
if ($env:BOB_MONITOR_SYNC_MIN_INTERVAL_SEC -match '^\d+$') {
    $SyncMinIntervalSec = [int]$env:BOB_MONITOR_SYNC_MIN_INTERVAL_SEC
}
if ($env:BOB_MONITOR_SKIP_SYNC -match '^(1|true|yes)$') { $SkipSync = $true }
if ($SyncTimeoutSec -lt 5) { $SyncTimeoutSec = 5 }
if ($SyncTimeoutSec -gt 120) { $SyncTimeoutSec = 120 }
# FR #9435: tip-fresh = local tools\monitor probe is same age or newer than tip sibling copy.
function Test-BobMonitorTipFresh([string]$InstallHere, [string]$BobRoot) {
    $local = Join-Path $InstallHere 'tools\monitor\stale_digest.py'
    if (-not (Test-Path -LiteralPath $local)) { return $false }
    $cands = @()
    if ($BobRoot) {
        $ai = Split-Path -Parent $BobRoot
        if ($ai) { $cands += (Join-Path $ai 'jeeves\tools\monitor\stale_digest.py') }
        $cands += (Join-Path $BobRoot 'jeeves\tools\monitor\stale_digest.py')
    }
    $tip = ''
    foreach ($c in $cands) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            try {
                $a = [string](Resolve-Path -LiteralPath $c).Path
                $b = [string](Resolve-Path -LiteralPath $local).Path
                if (-not [string]::Equals($a, $b, [StringComparison]::OrdinalIgnoreCase)) { $tip = $c; break }
            } catch { $tip = $c; break }
        }
    }
    if (-not $tip) { return $false }
    try {
        $lt = (Get-Item -LiteralPath $local).LastWriteTimeUtc
        $tt = (Get-Item -LiteralPath $tip).LastWriteTimeUtc
        return ($lt -ge $tt)
    } catch { return $false }
}
if ($syncMon) {
    $doSync = $true
    if ($SkipSync) {
        Write-Warning 'FR #9435 skip sync: -SkipSync / BOB_MONITOR_SKIP_SYNC'
        $doSync = $false
    } elseif (Test-BobMonitorTipFresh -InstallHere $here -BobRoot $bobRoot) {
        Write-Warning 'FR #9435 skip sync: tools\monitor already tip-fresh'
        $doSync = $false
    }
    $stamp = Join-Path $here '.bobiverse-monitor-last-sync'
    if (-not $DryRun -and $SyncMinIntervalSec -gt 0 -and (Test-Path -LiteralPath $stamp)) {
        try {
            $ageSec = ([datetime]::UtcNow - (Get-Item -LiteralPath $stamp).LastWriteTimeUtc).TotalSeconds
            if ($ageSec -lt $SyncMinIntervalSec) {
                Write-Warning ("FR #9350 skip sync: last sync {0:N0}s ago < MinInterval={1}s" -f $ageSec, $SyncMinIntervalSec)
                $doSync = $false
            }
        } catch { }
    }
    if ($doSync) {
        # FR #9350: never call Sync in-process. A hung fetch leaves the wrapper with empty
        # stdout and never reaches tools\monitor\*.py. Bound WaitForExit; kill and proceed.
        $outLog = Join-Path $env:TEMP ("jeeves-mon-sync-{0}.out.log" -f $PID)
        $errLog = Join-Path $env:TEMP ("jeeves-mon-sync-{0}.err.log" -f $PID)
        $argList = @(
            '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', $syncMon, '-Product', 'jeeves', '-InstallRoot', $here
        )
        if ($DryRun) { $argList += '-DryRun' }
        $p = $null
        try {
            $p = Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList $argList `
                -PassThru -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog
            $ms = [Math]::Max(5000, $SyncTimeoutSec * 1000)
            if (-not $p.WaitForExit($ms)) {
                # FR #9435: kill process tree (hung git grandchildren inherit Sync powershell).
                try {
                    if (-not $p.HasExited) {
                        Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" -ArgumentList @('/PID', [string]$p.Id, '/T', '/F') -Wait -WindowStyle Hidden | Out-Null
                    }
                } catch {
                    try { if (-not $p.HasExited) { $p.Kill() } } catch { }
                }
                Write-Warning ("FR #9350/#9435 sync-monitor timeout after {0}s; proceeding with existing tools\monitor" -f $SyncTimeoutSec)
            } elseif ($p.ExitCode -ne 0) {
                Write-Warning ("FR #9350 sync-monitor exit={0}; proceeding with existing tools\monitor" -f $p.ExitCode)
            }
        } catch {
            Write-Warning ("FR #9007/#9350 sync-monitor before check: {0}" -f $_.Exception.Message)
        } finally {
            if ($p) { try { $p.Dispose() } catch { } }
            # Stamp after every attempt so a hanging Sync does not re-fire every check.
            if (-not $DryRun) {
                try {
                    [IO.File]::WriteAllText($stamp, ([datetime]::UtcNow.ToString('o')))
                } catch { }
            }
        }
    }
}
$py = Join-Path $here "tools\monitor\$Check.py"
if (-not (Test-Path -LiteralPath $py)) {
    # Soft-skip: tip tree may lag AGENTS.md check list (non-chair / sparse sync). FR #9066.
    Write-Output (@{ check = $Check; ok = $true; skipped = $true; reason = "missing $py" } | ConvertTo-Json -Compress)
    exit 0
}
$python = $null
foreach ($c in @('python.exe', 'py.exe')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { Write-Error 'python.exe not found'; exit 2 }
$argv = @($py)
if ($DryRun) { $argv += '--dry-run' }
if ($ChairHome) { $argv += @('--chair-home', $ChairHome) }
if ($DigestHome) { $argv += @('--digest-home', $DigestHome) }
& $python @argv
exit $LASTEXITCODE
