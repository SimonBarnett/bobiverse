#requires -Version 5.1
<#
.SYNOPSIS
  Snapshot Grok Build / BobBridge usage on this Windows box.
.PARAMETER Json
  Emit a single JSON object instead of human text.
#>
[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Hover
)

$ErrorActionPreference = 'Continue'
$homeGrok = Join-Path $env:USERPROFILE '.grok'
$grokExe = Join-Path $homeGrok 'bin\grok.exe'

function Get-SubscriptionDisplay {
    $path = Join-Path $homeGrok 'settings_cache.json'
    if (-not (Test-Path $path)) { return $null }
    try {
        $wrap = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $wrap.payload) { return $null }
        $payload = $wrap.payload | ConvertFrom-Json
        $s = $payload.settings
        return [pscustomobject]@{
            subscription_tier_display = $s.subscription_tier_display
            allow_access              = $s.allow_access
            default_model             = $s.default_model
            release_channel           = $s.release_channel
            fetched_at                = $payload.fetched_at
            grok_version_reported     = $payload.grok_version
        }
    } catch {
        return $null
    }
}

function Get-GrokDu {
    if (-not (Test-Path $grokExe)) { return $null }
    try {
        $raw = & $grokExe du --json 2>$null
        if (-not $raw) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch { return $null }
}

function Get-ActiveSessionsFile {
    $path = Join-Path $homeGrok 'active_sessions.json'
    if (-not (Test-Path $path)) { return @() }
    try {
        return @(Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch { return @() }
}

function Get-SessionUsage([string]$SessionId) {
    if (-not (Test-Path $grokExe)) { return $null }
    try {
        $out = & $grokExe usage $SessionId 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            return [pscustomobject]@{ session_id = $SessionId; ok = $false; detail = ($out.Trim()) }
        }
        return [pscustomobject]@{ session_id = $SessionId; ok = $true; detail = ($out.Trim()) }
    } catch {
        return [pscustomobject]@{ session_id = $SessionId; ok = $false; detail = "$_" }
    }
}

function Try-ImportBobBridge {
    foreach ($root in @('C:\ai\agentic_build', 'D:\ai\agentic_build', 'C:\src\agentic_build')) {
        $psd = Join-Path $root 'src\BobBridge.psd1'
        if (Test-Path $psd) {
            Import-Module $psd -Force -ErrorAction SilentlyContinue
            return $root
        }
    }
    return $null
}

$now = Get-Date
$sub = Get-SubscriptionDisplay
$procs = @(Get-Process grok -ErrorAction SilentlyContinue | Select-Object Id, StartTime, CPU, @{n='WS_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}})

$bobRoot = Try-ImportBobBridge
$health = $null
$builds = @()
$week = $null
if ($bobRoot -and (Get-Command Get-BobHealth -ErrorAction SilentlyContinue)) {
    try { $health = Get-BobHealth } catch { $health = $null }
    try {
        if (Get-Command Get-BobBuilds -ErrorAction SilentlyContinue) {
            $builds = @(Get-BobBuilds -ErrorAction SilentlyContinue)
        }
    } catch { $builds = @() }
}
if (Get-Command Get-BobWeeklyRemaining -ErrorAction SilentlyContinue) {
    try { $week = Get-BobWeeklyRemaining } catch { $week = $null }
}

if ($Hover) {
    if (Get-Command Get-BobTrayHover -ErrorAction SilentlyContinue) {
        $h = Get-BobTrayHover
        $h | ConvertTo-Json -Compress -Depth 6
    }
    else {
        Write-Output '{"title":"Bob Fleet","scope":"local-store","short":"idle","body":"weekly remaining  n/a","remaining_pct":null,"remaining_kind":"weekly"}'
    }
    return
}

$du = Get-GrokDu
$active = @(Get-ActiveSessionsFile)

$recentIds = @()
if (Test-Path $grokExe) {
    try {
        $list = & $grokExe sessions list 2>&1 | Out-String
        foreach ($m in [regex]::Matches($list, '(?i)\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b')) {
            if ($recentIds -notcontains $m.Groups[1].Value) { $recentIds += $m.Groups[1].Value }
            if ($recentIds.Count -ge 5) { break }
        }
    } catch { }
}
foreach ($a in $active) {
    if ($a.session_id -and ($recentIds -notcontains $a.session_id)) {
        $recentIds = @($a.session_id) + $recentIds
    }
}
$usageRows = @()
foreach ($id in ($recentIds | Select-Object -First 5)) {
    $usageRows += ,(Get-SessionUsage $id)
}

$report = [ordered]@{
    generated_at_local = $now.ToString('yyyy-MM-dd HH:mm:ss zzz')
    hostname           = $env:COMPUTERNAME
    windows_user       = "$env:USERDOMAIN\$env:USERNAME"
    grok_home          = $homeGrok
    grok_exe_present   = [bool](Test-Path $grokExe)
    subscription       = $sub
    bob_bridge_root    = $bobRoot
    health             = $health
    weekly_remaining   = if ($week) {
        [ordered]@{
            # FR #427: Grok 1.0.41 may omit creditUsagePercent — keep null, never cast to 0.
            remaining_pct = $(if ($null -ne $week.remaining_pct -and [string]$week.remaining_pct -ne '') { [int]$week.remaining_pct } else { $null })
            used_pct      = $(if ($null -ne $week.used_pct -and [string]$week.used_pct -ne '') { [int]$week.used_pct } else { $null })
            fetched_at    = [string]$week.fetched_at
            period_end    = $(if ($week.period_end) { [string]$week.period_end } else { $null })
            source        = [string]$week.source
            kind          = [string]$week.kind
            format        = $(if ($week.format) { [string]$week.format } else { $null })
        }
    } else { $null }
    grok_processes     = $procs
    active_sessions    = $active
    bob_builds         = $builds
    disk               = if ($du) {
        [ordered]@{
            total_bytes = $du.total_bytes
            total_gb    = [math]::Round(($du.total_bytes / 1GB), 2)
            top_level   = @($du.top_level_dirs | Select-Object -First 8 name, bytes)
        }
    } else { $null }
    session_usage      = $usageRows
}

if ($Json) {
    $report | ConvertTo-Json -Depth 8
    return
}

Write-Host "=== Bob box usage ==="
Write-Host "When:     $($report.generated_at_local)"
Write-Host "Host:     $($report.hostname)  ($($report.windows_user))"
if ($sub) {
    Write-Host "Tier:     $($sub.subscription_tier_display)  allow_access=$($sub.allow_access)  model=$($sub.default_model)"
    Write-Host "Settings: fetched $($sub.fetched_at)  cli $($sub.grok_version_reported)"
} else {
    Write-Host "Tier:     (settings_cache missing or unreadable)"
}
if ($health) {
    $ghLine = ''
    if ($health.gh_posting) {
        $g = $health.gh_posting
        $ghLine = " gh_posting_ready=$($g.issue_posting_ready)"
    }
    Write-Host "Health:   ok=$($health.ok) grok=$($health.grok_version) logged_in=$($health.logged_in) workers=$($health.worker_count) watcher_up=$($health.watcher_up) last_seen_age_sec=$($health.last_seen_age_sec)$ghLine"
} elseif ($bobRoot) {
    Write-Host "Health:   BobBridge at $bobRoot but Get-BobHealth failed"
} else {
    Write-Host "Health:   BobBridge not found on known roots"
}
if ($week -and $null -ne $week.remaining_pct -and [string]$week.remaining_pct -ne '') {
    Write-Host ("Weekly:   remaining {0}% (used {1}%) source={2}" -f $week.remaining_pct, $week.used_pct, $week.source)
} elseif ($week -and $week.period_end) {
    # Grok 1.0.41+: period known, usage % unknown (FR #427)
    Write-Host ("Weekly:   n/a (usage unknown; until reset {0}) source={1}" -f $week.period_end, $week.source)
} else {
    Write-Host "Weekly:   n/a (no weekly billing period / creditUsagePercent)"
}
Write-Host "Processes: $($procs.Count) grok.exe"
foreach ($p in $procs) {
    Write-Host ("  pid={0} start={1} cpu={2} ws_mb={3}" -f $p.Id, $p.StartTime, $p.CPU, $p.WS_MB)
}
Write-Host "Active sessions file: $($active.Count)"
foreach ($a in $active) {
    Write-Host ("  {0} pid={1} cwd={2}" -f $a.session_id, $a.pid, $a.cwd)
}
if ($builds.Count -gt 0) {
    Write-Host "BobBridge builds: $($builds.Count)"
    foreach ($b in ($builds | Select-Object -First 12)) {
        $id = if ($b.id) { $b.id } elseif ($b.JobId) { $b.JobId } else { $b }
        $st = if ($b.status) { $b.status } elseif ($b.State) { $b.State } else { '?' }
        Write-Host "  $id  $st"
    }
} else {
    Write-Host "BobBridge builds: (none listed / unavailable)"
}
if ($report.disk) {
    Write-Host ("Disk ~/.grok: {0} GB ({1} bytes)" -f $report.disk.total_gb, $report.disk.total_bytes)
    foreach ($d in $report.disk.top_level) {
        Write-Host ("  {0}: {1:N0} bytes" -f $d.name, $d.bytes)
    }
} else {
    Write-Host "Disk ~/.grok: (grok du unavailable)"
}
Write-Host "Session usage (recent, may be empty while running):"
foreach ($u in $usageRows) {
    if (-not $u) { continue }
    if ($u.ok) {
        Write-Host "--- $($u.session_id) ---"
        Write-Host $u.detail
    } else {
        Write-Host ("  {0}: {1}" -f $u.session_id, $u.detail)
    }
}
Write-Host "=== end ==="