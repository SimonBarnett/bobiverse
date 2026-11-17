function Test-BobJobProcess {
    param(
        [string]$SessionId,
        [string[]]$CommandLines
    )
    if (-not $SessionId) { return $false }
    $esc = [regex]::Escape($SessionId)
    if ($null -ne $CommandLines) {
        foreach ($line in $CommandLines) {
            if ($line -and ($line -match $esc)) { return $true }
        }
        return $false
    }
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $esc })
    return ($hits.Count -gt 0)
}

function Get-BobStallAlerts {
    param(
        $Seen,
        [int]$StallSec = 600,
        [int]$HeartbeatStaleSec = 90,
        # FR #7998: tests and the tray pass one process snapshot. Null means query once.
        $ProcessRows
    )
    if (-not $Seen) { throw 'Seen hashtable required' }
    if (-not $Seen['inbox']) { $Seen['inbox'] = @{} }
    if (-not $Seen['running']) { $Seen['running'] = @{} }
    if (-not $Seen['stall']) { $Seen['stall'] = @{} }
    $WipPattern = '(?i)(\bstarting with\b|\bthen commit\b|\bworking on\b|\babout to\b)'
    $alerts = New-Object System.Collections.Generic.List[string]

    # FR #7998: local watcher and last-seen only. The full health command
    # runs the grok CLI and a bot health call at 30s each and blows the 45s step.
    if ($null -eq $ProcessRows) {
        $ProcessRows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    }
    $lines = New-Object System.Collections.Generic.List[string]
    $watcherUp = $false
    foreach ($p in @($ProcessRows)) {
        $cmd = [string]$p.CommandLine
        $name = [string]$p.Name
        if ($cmd) { [void]$lines.Add($cmd) }
        if (-not $watcherUp -and $name -match '^(powershell|pwsh)\.exe$' -and $cmd -and $cmd -match 'Watch-BobJobs\.ps1' -and $cmd -notmatch '(?i)-Once\b') {
            $watcherUp = $true
        }
    }
    $commandLines = $lines.ToArray()
    $rec = $null
    try { $rec = Get-BobMachineRecord } catch { $rec = $null }
    $age = $null
    try { $age = Get-BobLastSeenAgeSec -Record $rec } catch { $age = $null }
    $lastSeen = if ($rec) { [string]$rec.lastSeen } else { $null }
    $heartbeatStale = ($null -ne $age -and [int]$age -gt $HeartbeatStaleSec)
    $runningNow = @(Get-BobBuilds -Lane running -ErrorAction SilentlyContinue)
    $busy = $runningNow.Count -gt 0
    $watcherDead = (-not $watcherUp) -or ($heartbeatStale -and -not $busy)
    if ($watcherDead -and -not (Test-BobWatcherInstalled)) { $watcherDead = $false }
    if ($watcherDead) {
        if (-not $Seen.watcher_down) {
            $Seen.watcher_down = $true
            $alerts.Add("ACTION_REQUIRED: watcher_down watcher_up=$watcherUp last_seen=$lastSeen age_sec=$age running=$($runningNow.Count)")
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
        if (-not $id) { continue }
        $nowRun[$id] = $true
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
        $alive = Test-BobJobProcess -SessionId $sid -CommandLines $commandLines
        if ((-not $alive) -and $watcherUp) { continue }
        if ((-not $alive) -and $claimedAge -ge $HeartbeatStaleSec -and -not $Seen.running.ContainsKey($id)) {
            $Seen.running[$id] = $true
            $alerts.Add("ACTION_REQUIRED: running_orphan $id session=$sid age_sec=$claimedAge")
        }
    }
    foreach ($k in @($Seen.running.Keys)) {
        if (-not $nowRun.ContainsKey($k)) { $Seen.running.Remove($k) }
    }

    # Agent stall uses a short bot list (5s). Never the 30s health or agent list path.
    $agents = @()
    $botUp = $false
    if (Get-Command Test-GrokBotAvailable -ErrorAction SilentlyContinue) {
        try { $botUp = [bool](Test-GrokBotAvailable) } catch { $botUp = $false }
    }
    if ($botUp -and (Get-Command Invoke-GrokBotApi -ErrorAction SilentlyContinue)) {
        try {
            $listed = Invoke-GrokBotApi -Action list -TimeoutSec 5
            if ($listed.Parsed -and $listed.Parsed.agents) { $agents = @($listed.Parsed.agents) }
        }
        catch { $agents = @() }
    }
    if ($agents.Count -gt 0) {
        $nowStall = @{}
        $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        foreach ($a in $agents) {
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
