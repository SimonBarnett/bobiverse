function Test-BobJobProcess {
    param([string]$SessionId)
    if (-not $SessionId) { return $false }
    $esc = [regex]::Escape($SessionId)
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $esc })
    return ($hits.Count -gt 0)
}

function Get-BobStallAlerts {
    param(
        $Seen,
        [int]$StallSec = 600,
        [int]$HeartbeatStaleSec = 90
    )
    if (-not $Seen) { throw 'Seen hashtable required' }
    if (-not $Seen['inbox']) { $Seen['inbox'] = @{} }
    if (-not $Seen['running']) { $Seen['running'] = @{} }
    if (-not $Seen['stall']) { $Seen['stall'] = @{} }
    $WipPattern = '(?i)(\bstarting with\b|\bthen commit\b|\bworking on\b|\babout to\b)'
    $alerts = New-Object System.Collections.Generic.List[string]
    $health = Get-BobHealth
    $watcherUp = [bool]$health.watcher_up
    $age = $health.last_seen_age_sec
    $heartbeatStale = ($null -ne $age -and [int]$age -gt $HeartbeatStaleSec)
    $runningNow = @(Get-BobBuilds -Lane running -ErrorAction SilentlyContinue)
    $busy = $runningNow.Count -gt 0
    $watcherDead = (-not $watcherUp) -or ($heartbeatStale -and -not $busy)
    if ($watcherDead) {
        if (-not $Seen.watcher_down) {
            $Seen.watcher_down = $true
            $alerts.Add("ACTION_REQUIRED: watcher_down watcher_up=$watcherUp last_seen=$($health.last_seen) age_sec=$age running=$($runningNow.Count)")
        }
    }
    else {
        $Seen.watcher_down = $false
    }

    $inbox = @(Get-BobBuilds -Lane inbox -ErrorAction SilentlyContinue)
    $nowInbox = @{}
    foreach ($j in $inbox) {
        $id = [string]$j.id
        if (-not $id) { continue }
        $nowInbox[$id] = $true
        $jobAge = $null
        if ($j.createdAt) {
            try {
                $t = [datetime]::Parse($j.createdAt, $null, [Globalization.DateTimeStyles]::RoundtripKind)
                $jobAge = [int]([datetime]::UtcNow - $t.ToUniversalTime()).TotalSeconds
            }
            catch { }
        }
        if ($jobAge -ge $HeartbeatStaleSec -and -not $busy -and -not $Seen.inbox.ContainsKey($id)) {
            $Seen.inbox[$id] = $true
            $alerts.Add("ACTION_REQUIRED: inbox_stale $id age_sec=$jobAge")
        }
    }
    foreach ($k in @($Seen.inbox.Keys)) {
        if (-not $nowInbox.ContainsKey($k)) { $Seen.inbox.Remove($k) }
    }

    $nowRun = @{}
    foreach ($j in $runningNow) {
        $id = [string]$j.id
        if (-not $id) { continue }`r`n        $nowRun[$id] = $true
        $sid = [string]$j.sessionId
        if (-not $sid) { $sid = $id }
        $claimedAge = $null
        if ($j.claimedAt) {
            try {
                $t = [datetime]::Parse($j.claimedAt, $null, [Globalization.DateTimeStyles]::RoundtripKind)
                $claimedAge = [int]([datetime]::UtcNow - $t.ToUniversalTime()).TotalSeconds
            }
            catch { }
        }
        $alive = Test-BobJobProcess -SessionId $sid
        if ((-not $alive) -and $watcherUp) { continue }
        if ((-not $alive) -and $claimedAge -ge $HeartbeatStaleSec -and -not $Seen.running.ContainsKey($id)) {
            $Seen.running[$id] = $true
            $alerts.Add("ACTION_REQUIRED: running_orphan $id session=$sid age_sec=$claimedAge")
        }
    }
    foreach ($k in @($Seen.running.Keys)) {
        if (-not $nowRun.ContainsKey($k)) { $Seen.running.Remove($k) }
    }

    if ($health.grokbot) {
        $nowStall = @{}
        $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        foreach ($a in @(Get-BobAgents)) {
            $name = [string]$a.name
            $text = [string]$a.last
            $act = 0
            if ($a.lastActivityAt) { [void][int64]::TryParse([string]$a.lastActivityAt, [ref]$act) }
            $idleSec = if ($act -gt 0) { [int](($nowMs - $act) / 1000) } else { 0 }
            $wip = ($text -and ($text -match $WipPattern))
            if ($wip -and $idleSec -ge $StallSec) {
                $nowStall[$name] = $true
                if ($Seen.stall[$name] -ne $act) {
                    $Seen.stall[$name] = $act
                    $snip = $text
                    if ($snip.Length -gt 180) { $snip = $snip.Substring(0, 180) }
                    $alerts.Add("ACTION_REQUIRED: agent_stall $name idle_sec=$idleSec last=$snip")
                }
            }
        }
        foreach ($k in @($Seen.stall.Keys)) {
            if (-not $nowStall.ContainsKey($k)) { $Seen.stall.Remove($k) }
        }
    }
    return @($alerts.ToArray())
}
