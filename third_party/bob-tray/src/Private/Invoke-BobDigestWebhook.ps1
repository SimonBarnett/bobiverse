function Get-BobDigestWebhookLastPostPath {
    Join-Path (Get-BridgeRoot) 'digest-webhook-last.json'
}

function Get-BobDigestWebhookCaptureDir {
    if ($env:BOB_REPORT_CAPTURE_DIR -and $env:BOB_REPORT_CAPTURE_DIR.Trim()) {
        return [IO.Path]::GetFullPath($env:BOB_REPORT_CAPTURE_DIR.Trim())
    }
    return $null
}

function Get-BobDigestWebhookReportUrl {
    $cfg = Get-BobiverseConfig
    if ($cfg -and $cfg.reportUrl -and [string]$cfg.reportUrl.Trim()) {
        return [string]$cfg.reportUrl.Trim()
    }
    if ($env:BOB_REPORT_URL -and $env:BOB_REPORT_URL.Trim()) {
        return [string]$env:BOB_REPORT_URL.Trim()
    }
    return $null
}

function ConvertTo-BobDigestWebhookPayload {
    param(
        [string]$WorkingOn,
        [string]$Repo,
        [string]$MachineId
    )
    $id = $MachineId
    if (-not $id) { $id = Get-ThisMachineId }
    $payload = [ordered]@{
        online     = $true
        status     = 'ok'
        working_on = $WorkingOn
    }
    if ($id) { $payload['id'] = $id }
    if ($Repo) { $payload['repo'] = $Repo }
    return [pscustomobject]$payload
}

function Get-BobDigestUsageWebhookLastPostPath {
    Join-Path (Get-BridgeRoot) 'digest-usage-webhook-last.json'
}

function Get-BobDigestWebhookPoolSnapshot {
    param($Pools)
    $parts = @()
    foreach ($p in @($Pools)) {
        if (-not $p) { continue }
        $gid = [string]$p.group_id
        $rem = $p.remaining_pct
        $pe = $p.period_end
        if ($gid) { $parts += ($gid + '=' + $(if ($null -eq $rem) { 'n/a' } else { [string]$rem }) + '@' + $(if ($pe) { [string]$pe } else { '-' })) }
    }
    return ($parts -join ';')
}

function Get-BobFleetCursorPoolsSnapshotPath {
    Join-Path (Get-BridgeRoot) 'fleet-cursor-pools-snapshots.json'
}

function Save-BobFleetCursorPoolsSnapshot {
    param(
        [Parameter(Mandatory)][string]$MachineId,
        $Pools
    )
    $path = Get-BobFleetCursorPoolsSnapshotPath
    $map = @{}
    $existing = Read-JsonFile $path
    if ($existing) {
        foreach ($p in $existing.PSObject.Properties) { $map[[string]$p.Name] = $p.Value }
    }
    $rows = @()
    foreach ($pool in @($Pools)) {
        if (-not $pool) { continue }
        $rows += ,[pscustomobject]@{
            group_id      = [string]$pool.group_id
            remaining_pct = $pool.remaining_pct
            period_end    = $(if ($pool.period_end) { [string]$pool.period_end } else { $null })
        }
    }
    $map[$MachineId] = [pscustomobject]@{ at = [DateTime]::UtcNow.ToString('o'); pools = @($rows) }
    Write-JsonFile $path ([pscustomobject]$map)
}

function Merge-BobFleetCursorPoolsLesser {
    param($LocalPools)
    $byGroup = @{}
    foreach ($pool in @($LocalPools)) {
        if (-not $pool -or -not $pool.group_id) { continue }
        $gid = [string]$pool.group_id
        $rem = $pool.remaining_pct
        if ($null -eq $rem) { continue }
        try { $rem = [int]$rem } catch { continue }
        if (-not $byGroup.ContainsKey($gid) -or $rem -lt $byGroup[$gid].remaining_pct) {
            $byGroup[$gid] = $pool
        }
    }
    $path = Get-BobFleetCursorPoolsSnapshotPath
    $snap = Read-JsonFile $path
    $ircHome = $null
    try { $ircHome = Get-BobIrcHome } catch { }
    if ($ircHome) {
        $peersDir = Join-Path $ircHome 'bob-peers'
        if (Test-Path -LiteralPath $peersDir) {
            foreach ($pf in @(Get-ChildItem -LiteralPath $peersDir -Filter '*.json' -ErrorAction SilentlyContinue)) {
                $peer = Read-JsonFile $pf.FullName
                if (-not $peer) { continue }
                $peerPools = @()
                if ($peer.cursor_pools) { $peerPools = @($peer.cursor_pools) }
                elseif ($peer.pools) { $peerPools = @($peer.pools) }
                foreach ($row in @($peerPools)) {
                    if (-not $row) { continue }
                    $gid = [string]$row.group_id
                    if (-not $gid -and $row.id) { $gid = [string]$row.id }
                    if (-not $gid -and $row.group) { $gid = Normalize-BobCursorSpendingGroupId ([string]$row.group) }
                    if (-not $gid) { continue }
                    $rem = $row.remaining_pct
                    if ($null -eq $rem -and $null -ne $row.remaining) { $rem = $row.remaining }
                    if ($null -eq $rem) { continue }
                    try { $rem = [int]$rem } catch { continue }
                    if (-not $byGroup.ContainsKey($gid) -or $rem -lt $byGroup[$gid].remaining_pct) {
                        $byGroup[$gid] = [pscustomobject]@{
                            group_id       = $gid
                            group_label    = $(if ($row.group_label) { [string]$row.group_label } else { $gid })
                            remaining_pct  = $rem
                            period_end     = $(if ($row.period_end) { [string]$row.period_end } else { $null })
                            pct_label      = ('{0}%' -f $rem)
                        }
                    }
                }
            }
        }
    }
    if ($snap) {
        foreach ($prop in @($snap.PSObject.Properties)) {
            $ent = $prop.Value
            if (-not $ent -or -not $ent.pools) { continue }
            foreach ($row in @($ent.pools)) {
                if (-not $row -or -not $row.group_id) { continue }
                $gid = [string]$row.group_id
                $rem = $row.remaining_pct
                if ($null -eq $rem) { continue }
                try { $rem = [int]$rem } catch { continue }
                if (-not $byGroup.ContainsKey($gid) -or $rem -lt $byGroup[$gid].remaining_pct) {
                    $byGroup[$gid] = [pscustomobject]@{
                        group_id       = $gid
                        group_label    = $gid
                        remaining_pct  = $rem
                        period_end     = $(if ($row.period_end) { [string]$row.period_end } else { $null })
                        pct_label      = ('{0}%' -f $rem)
                    }
                }
            }
        }
    }
    $merged = @()
    foreach ($pool in @($LocalPools)) {
        if (-not $pool) { continue }
        $gid = [string]$pool.group_id
        if ($byGroup.ContainsKey($gid)) {
            $merged += $byGroup[$gid]
        }
        else {
            $merged += $pool
        }
    }
    if ($merged.Count -eq 0) { return @($LocalPools) }
    return @($merged)
}

function Build-BobChairUsageWebhookPayload {
    param([string]$MachineId)
    $id = $MachineId
    if (-not $id) { $id = Get-ThisMachineId }
    $cursorWeek = $null
    try { $cursorWeek = Get-BobCursorAgentWeeklyRemaining } catch { }
    $pools = @(Get-BobCursorPoolsForTray -MachineId $id -LocalCursorDoc $cursorWeek -PcentRows @())
    $pools = @(Merge-BobFleetCursorPoolsLesser -LocalPools $pools)
    $weekly = $null
    $weeklyEnd = $null
    try {
        $w = Get-BobWeeklyRemaining
        if ($w -and $null -ne $w.remaining_pct) { $weekly = [int]$w.remaining_pct }
        if ($w -and $w.period_end) { $weeklyEnd = [string]$w.period_end }
    }
    catch { }
    $poolRows = @()
    foreach ($p in $pools) {
        if (-not $p) { continue }
        $poolRows += ,[pscustomobject]@{
            group_id       = [string]$p.group_id
            group_label    = [string]$p.group_label
            remaining_pct  = $p.remaining_pct
            period_end     = $(if ($p.period_end) { [string]$p.period_end } else { $null })
            pct_label      = [string]$p.pct_label
        }
    }
    if ($poolRows.Count -eq 0) {
        foreach ($grp in @(Get-BobCursorSpendingGroupCatalog)) {
            $poolRows += ,[pscustomobject]@{
                group_id      = [string]$grp.id
                group_label   = [string]$grp.label
                remaining_pct = $null
                period_end    = $null
                pct_label     = 'n/a'
            }
        }
    }
    return [pscustomobject]@{
        online        = $true
        status        = 'ok'
        id            = $id
        local_weekly  = [pscustomobject]@{
            remaining_pct = $weekly
            period_end    = $weeklyEnd
        }
        cursor_pools  = @($poolRows)
        pools_sig     = Get-BobDigestWebhookPoolSnapshot -Pools $poolRows
    }
}

function Test-BobDigestUsageWebhookChanged {
    param($Payload)
    $lastPath = Get-BobDigestUsageWebhookLastPostPath
    $prev = Read-JsonFile $lastPath
    if (-not $prev) { return $true }
    $sig = [string]$Payload.pools_sig
    $prevSig = [string]$prev.pools_sig
    if ($sig -ne $prevSig) { return $true }
    $w = $Payload.local_weekly
    $pw = $prev.local_weekly
    if ($w -and $pw) {
        if ([string]$w.remaining_pct -ne [string]$pw.remaining_pct) { return $true }
        if ([string]$w.period_end -ne [string]$pw.period_end) { return $true }
    }
    return $false
}

function Invoke-BobRepoPairChairUsageWebhookIfChanged {
    [CmdletBinding()]
    param([switch]$Force)
    $payload = Build-BobChairUsageWebhookPayload
    try {
        $mid = Get-ThisMachineId
        if ($payload -and $payload.cursor_pools) {
            Save-BobFleetCursorPoolsSnapshot -MachineId $mid -Pools @($payload.cursor_pools)
        }
    }
    catch { }
    if (-not $Force -and -not (Test-BobDigestUsageWebhookChanged -Payload $payload)) {
        return [pscustomobject]@{ ok = $true; posted = $false; reason = 'unchanged' }
    }
    $cap = Get-BobDigestWebhookCaptureDir
    if ($cap) {
        New-Item -ItemType Directory -Force -Path $cap | Out-Null
        $n = (Get-ChildItem $cap -Filter 'usage-post-*.json' -ErrorAction SilentlyContinue).Count + 1
        $out = Join-Path $cap ('usage-post-{0}.json' -f $n)
        Write-JsonFile $out $payload
        Write-JsonFile (Get-BobDigestUsageWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $true; capture = $out }
    }
    $url = Get-BobDigestWebhookReportUrl
    if (-not $url) {
        Write-JsonFile (Get-BobDigestUsageWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $false; reason = 'no_report_url' }
    }
    $secret = $null
    if ($env:BOB_REPORT_SECRET -and $env:BOB_REPORT_SECRET.Trim()) {
        $secret = [string]$env:BOB_REPORT_SECRET.Trim()
    }
    elseif ($env:BOB_IRC_HOME -and $env:BOB_IRC_HOME.Trim()) {
        $sf = Join-Path $env:BOB_IRC_HOME.Trim() 'report.secret'
        if (Test-Path $sf) {
            try { $secret = ([IO.File]::ReadAllText($sf)).Trim() } catch { }
        }
    }
    $headers = @{ 'Content-Type' = 'application/json' }
    if ($secret) { $headers['X-Bob-Secret'] = $secret }
    $json = ($payload | ConvertTo-Json -Depth 8 -Compress)
    try {
        $null = Invoke-RestMethod -Uri $url -Method Post -Body $json -Headers $headers -TimeoutSec 30
        Write-JsonFile (Get-BobDigestUsageWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $true; url = $url }
    }
    catch {
        return [pscustomobject]@{ ok = $false; posted = $false; error = $_.Exception.Message }
    }
}

function Test-BobDigestWebhookPayloadChanged {
    param($Payload)
    $lastPath = Get-BobDigestWebhookLastPostPath
    $prev = Read-JsonFile $lastPath
    if (-not $prev) { return $true }
    $keys = @('online', 'status', 'working_on', 'repo', 'sha', 'model', 'fuel', 'weekly', 'cursor_label', 'pools_sig')
    foreach ($k in $keys) {
        $a = $null
        $b = $null
        if ($Payload.PSObject.Properties.Name -contains $k) { $a = [string]$Payload.$k }
        if ($prev.PSObject.Properties.Name -contains $k) { $b = [string]$prev.$k }
        if ($a -ne $b) { return $true }
    }
    if ($Payload.cursor_pools -or $prev.cursor_pools) {
        $a = Get-BobDigestWebhookPoolSnapshot -Pools @($Payload.cursor_pools)
        $b = Get-BobDigestWebhookPoolSnapshot -Pools @($prev.cursor_pools)
        if ($a -ne $b) { return $true }
    }
    return $false
}

function Invoke-BobDigestWebhookPost {
    [CmdletBinding()]
    param(
        [string]$WorkingOn,
        [string]$Repo,
        [string]$MachineId,
        [switch]$Force
    )
    $payload = ConvertTo-BobDigestWebhookPayload -WorkingOn $WorkingOn -Repo $Repo -MachineId $MachineId
    if (-not $Force -and -not (Test-BobDigestWebhookPayloadChanged -Payload $payload)) {
        return [pscustomobject]@{ ok = $true; posted = $false; reason = 'unchanged' }
    }
    $cap = Get-BobDigestWebhookCaptureDir
    if ($cap) {
        New-Item -ItemType Directory -Force -Path $cap | Out-Null
        $n = (Get-ChildItem $cap -Filter 'post-*.json' -ErrorAction SilentlyContinue).Count + 1
        $out = Join-Path $cap ('post-{0}.json' -f $n)
        Write-JsonFile $out $payload
        Write-JsonFile (Get-BobDigestWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $true; capture = $out }
    }
    $url = Get-BobDigestWebhookReportUrl
    if (-not $url) {
        Write-JsonFile (Get-BobDigestWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $false; reason = 'no_report_url' }
    }
    $secret = $null
    if ($env:BOB_REPORT_SECRET -and $env:BOB_REPORT_SECRET.Trim()) {
        $secret = [string]$env:BOB_REPORT_SECRET.Trim()
    }
    elseif ($env:BOB_IRC_HOME -and $env:BOB_IRC_HOME.Trim()) {
        $sf = Join-Path $env:BOB_IRC_HOME.Trim() 'report.secret'
        if (Test-Path $sf) {
            try { $secret = ([IO.File]::ReadAllText($sf)).Trim() } catch { }
        }
    }
    $headers = @{ 'Content-Type' = 'application/json' }
    if ($secret) { $headers['X-Bob-Secret'] = $secret }
    $json = ($payload | ConvertTo-Json -Depth 6 -Compress)
    try {
        $null = Invoke-RestMethod -Uri $url -Method Post -Body $json -Headers $headers -TimeoutSec 30
        Write-JsonFile (Get-BobDigestWebhookLastPostPath) $payload
        return [pscustomobject]@{ ok = $true; posted = $true; url = $url }
    }
    catch {
        return [pscustomobject]@{ ok = $false; posted = $false; error = $_.Exception.Message }
    }
}
