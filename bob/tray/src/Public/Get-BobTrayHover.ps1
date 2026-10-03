function Test-BobTrayLooksLikeSha {
    param([string]$Value)
    if (-not $Value) { return $true }
    $s = [string]$Value.Trim()
    if ($s -match '^(HEAD|[0-9a-fA-F]{7,40})$') { return $true }
    return $false
}

function Get-GitHubSlugFromCwd {
    param([string]$Cwd)
    $slug = $null
    if ($Cwd) {
        try {
            if (Get-Command git -ErrorAction SilentlyContinue) {
                $url = & git -C $Cwd remote get-url origin 2>$null
                if ($url -match 'github\.com[:/](?<slug>.+?)(?:\.git)?\s*$') {
                    $slug = $Matches['slug'].Trim().TrimEnd('/').Replace('\', '/')
                }
            }
        }
        catch { }
    }
    if ($slug -and ($slug -match '/') -and -not (Test-BobTrayLooksLikeSha $slug)) {
        return $slug
    }
    if ($Cwd) {
        try {
            $leaf = Split-Path $Cwd -Leaf
            if ($leaf -and -not (Test-BobTrayLooksLikeSha $leaf)) { return $leaf }
        }
        catch { }
    }
    return '?'
}

function Get-BobJobAge {
    param($ClaimedAt)
    if (-not $ClaimedAt) { return '?' }
    try {
        $t = [datetime]::Parse([string]$ClaimedAt, $null, [Globalization.DateTimeStyles]::RoundtripKind)
        if ($t.Kind -eq [DateTimeKind]::Unspecified) { $t = [datetime]::SpecifyKind($t, [DateTimeKind]::Utc) }
        $ts = [datetime]::UtcNow - $t.ToUniversalTime()
        if ($ts.TotalHours -ge 1) { return ('{0}h{1}m' -f [int]$ts.TotalHours, $ts.Minutes) }
        if ($ts.TotalMinutes -ge 1) { return ('{0}m' -f [int]$ts.TotalMinutes) }
        return ('{0}s' -f [int][math]::Max(0, $ts.TotalSeconds))
    }
    catch { return '?' }
}

function Get-ContextWindowTokens {
    try {
        $p = Join-Path $env:USERPROFILE '.grok\models_cache.json'
        if (-not (Test-Path $p)) { return 500000 }
        $d = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json
        $m = $d.models
        foreach ($name in @('grok-4.6', 'grok-4.5', 'grok-4')) {
            if ($m.$name -and $m.$name.info -and $m.$name.info.context_window) {
                return [int]$m.$name.info.context_window
            }
        }
    }
    catch { }
    return 500000
}

function Get-SessionContextRemaining {
    param([string]$Cwd, [string]$SessionId)
    if (-not $Cwd -or -not $SessionId) { return $null }
    $leaf = ([string]$Cwd).Replace('\', '%5C').Replace(':', '%3A')
    $usagePath = Join-Path $env:USERPROFILE (Join-Path '.grok\sessions' (Join-Path $leaf (Join-Path $SessionId 'usage.json')))
    if (-not (Test-Path $usagePath)) { return $null }
    try {
        $u = Get-Content $usagePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $s = $u.session
        if (-not $s) { return $null }
        $input = [int64]$s.inputTokens
        $cached = 0
        if ($s.cachedReadTokens) { $cached = [int64]$s.cachedReadTokens }
        $used = [math]::Max(0, $input - $cached)
        $window = Get-ContextWindowTokens
        if ($window -le 0) { return $null }
        $remain = [int][math]::Round(100.0 * [math]::Max(0, $window - $used) / $window)
        if ($remain -gt 100) { $remain = 100 }
        return [pscustomobject]@{
            remaining_pct = $remain
            used          = $used
            window        = $window
        }
    }
    catch { return $null }
}

function Get-BobWeeklyLogPath {
    if ($env:BOB_WEEKLY_LOG -and $env:BOB_WEEKLY_LOG.Trim()) {
        return $env:BOB_WEEKLY_LOG.Trim()
    }
    # Isolated Fake-Grok tests must not scrape the operator CLI log.
    $exe = [string]$env:BOB_GROK_EXE
    if ($exe -and ($exe -match '(?i)Fake-Grok')) { return $null }
    return (Join-Path $env:USERPROFILE '.grok\logs\unified.jsonl')
}

function Resolve-BobSeatMateWeekly {
    <#
    .SYNOPSIS
      Weekly % for a machine whose own Grok reading is stale/unmeasured (t785u): a seat-mate on the SAME Grok account
      (seat) whose reading is for the SAME weekly period (identical period_end instant) is the same pool.
    .OUTPUTS
      [int] or $null. Never used when the local reading is current (that stays authoritative, CAST IRON #150).
    #>
    param([string]$MachineId, $LocalWeek, $Seats, $WeeklyBy, $PeriodEndBy)
    if (-not $LocalWeek -or -not $LocalWeek.stale -or -not $LocalWeek.period_end) { return $null }
    $mine = $null
    try { $mine = [datetime]::Parse([string]$LocalWeek.period_end, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() } catch { return $null }
    foreach ($seat in @($Seats)) {
        $mates = @($seat.machines | ForEach-Object { [string]$_ })
        if ($mates -notcontains $MachineId) { continue }
        foreach ($sm in $mates) {
            if (-not $sm -or $sm -eq $MachineId) { continue }
            if (-not $WeeklyBy.ContainsKey($sm) -or $null -eq $WeeklyBy[$sm]) { continue }
            if (-not $PeriodEndBy.ContainsKey($sm) -or -not $PeriodEndBy[$sm]) { continue }
            try {
                $theirs = [datetime]::Parse([string]$PeriodEndBy[$sm], [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
            } catch { continue }
            if ([math]::Abs(($theirs - $mine).TotalSeconds) -lt 2) { return [int]$WeeklyBy[$sm] }
        }
    }
    return $null
}

function Step-BobWeeklyPeriodForward {
    <#
    .SYNOPSIS
      A Grok weekly reading whose period has ended is not a current figure (t785u).
    .NOTES
      The Grok CLI only logs 'billing: fetched credits config' while it is used. After the weekly period rolls over the
      last event describes the PREVIOUS period: its % is not this week's, and its period_end is in the past (the tray hid
      the whole row and the digest carried a stale 8% + a past reset). The weekly clock is exact (7 days), so the
      reading is rolled to the current period: remaining_pct = $null (unmeasured, never invented), period_end = the next
      reset, stale = $true (last_remaining_pct / last_period_end keep the old values). Current readings pass through.
    #>
    param($Weekly, [datetime]$UtcNow = [datetime]::UtcNow)
    if (-not $Weekly -or -not $Weekly.period_end) { return $Weekly }
    $pe = $null
    try { $pe = [datetime]::Parse([string]$Weekly.period_end, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() } catch { return $Weekly }
    $now = $UtcNow.ToUniversalTime()
    if ($pe -gt $now) { return $Weekly }
    $weeks = [int][math]::Ceiling(($now - $pe).TotalDays / 7.0)
    if ($weeks -lt 1) { $weeks = 1 }
    $next = $pe.AddDays(7 * $weeks)
    if ($next -le $now) { $next = $next.AddDays(7) }
    return [pscustomobject]@{
        remaining_pct      = $null
        used_pct           = $null
        fetched_at         = [string]$Weekly.fetched_at
        period_end         = $next.ToString('o')
        source             = ([string]$Weekly.source + ':period-rolled')
        kind               = 'weekly'
        format             = [string]$Weekly.format
        stale              = $true
        last_remaining_pct = $Weekly.remaining_pct
        last_period_end    = [string]$Weekly.period_end
    }
}

function Get-BobWeeklyRemaining {
    [CmdletBinding()]
    param([string]$LogPath, [datetime]$UtcNow = [datetime]::UtcNow)
    $w = Get-BobWeeklyRemainingRaw -LogPath $LogPath
    if (-not $w) { return $null }
    return (Step-BobWeeklyPeriodForward -Weekly $w -UtcNow $UtcNow)
}

function Get-BobWeeklyRemainingRaw {
    <#
    .SYNOPSIS
      Parse Grok CLI weekly remaining from unified.jsonl billing events.
    .NOTES
      FR #427: Grok 1.0.41 removed creditUsagePercent; keep period_end even when
      remaining_pct is unknown. Legacy ≤1.0.40 still uses creditUsagePercent.
      prepaidBalance/onDemandUsed/onDemandCap are .val objects on 1.0.41 — we do
      not invent a weekly % from them (out of scope: on-demand-only billing).
    #>
    [CmdletBinding()]
    param([string]$LogPath)
    if (-not $LogPath) { $LogPath = Get-BobWeeklyLogPath }
    if (-not $LogPath -or -not (Test-Path $LogPath)) { return $null }
    $raw = $null
    try {
        $fs = [IO.File]::Open($LogPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $pos = $fs.Length
            $chunk = 1MB
            while ($pos -gt 0 -and -not $raw) {
                $take = [int64][Math]::Min($chunk, $pos)
                $pos = $pos - $take
                [void]$fs.Seek($pos, [IO.SeekOrigin]::Begin)
                $buf = New-Object byte[] $take
                $n = $fs.Read($buf, 0, $take)
                $text = [Text.Encoding]::UTF8.GetString($buf, 0, $n)
                $lines = $text -split "`r?`n"
                $start = 0
                if ($pos -gt 0) { $start = 1 }
                for ($i = $lines.Length - 1; $i -ge $start; $i--) {
                    $ln = $lines[$i]
                    if ($ln -and $ln.Contains('billing: fetched credits config')) {
                        $raw = $ln.Trim()
                        break
                    }
                }
            }
        }
        finally { $fs.Dispose() }
    }
    catch { return $null }
    if (-not $raw) { return $null }
    try {
        $j = $raw | ConvertFrom-Json
        $cfg = $null
        if ($j.ctx -and $j.ctx.config) { $cfg = $j.ctx.config }
        elseif ($j.config) { $cfg = $j.config }
        if (-not $cfg) { return $null }
        $ptype = $null
        if ($cfg.currentPeriod -and $cfg.currentPeriod.type) { $ptype = [string]$cfg.currentPeriod.type }
        # Weekly only: accept WEEKLY or USAGE_PERIOD_TYPE_WEEKLY (Grok 1.0.41 enum).
        if (-not $ptype -or ($ptype -notmatch 'WEEKLY')) { return $null }
        $periodEnd = $null
        if ($cfg.currentPeriod -and $cfg.currentPeriod.end) { $periodEnd = [string]$cfg.currentPeriod.end }
        $fetchedAt = [string]$j.ts

        # Legacy Grok ≤1.0.40: scalar creditUsagePercent at config root.
        $usedRaw = $cfg.creditUsagePercent
        if ($null -ne $usedRaw -and -not [string]::IsNullOrWhiteSpace([string]$usedRaw)) {
            $used = [double]$usedRaw
            if ($used -lt 0 -or $used -gt 100) { return $null }
            $remain = [int][math]::Round(100.0 - $used)
            if ($remain -lt 0) { $remain = 0 }
            if ($remain -gt 100) { $remain = 100 }
            return [pscustomobject]@{
                remaining_pct = $remain
                used_pct      = [int][math]::Round($used)
                fetched_at    = $fetchedAt
                period_end    = $periodEnd
                source        = 'unified.jsonl:billing:creditUsagePercent'
                kind          = 'weekly'
                format        = 'legacy-1.0.40'
            }
        }

        # Grok 1.0.41+: no creditUsagePercent. Keep period_end for tray countdown;
        # do not invent remaining_pct from prepaidBalance/onDemand* (ambiguous).
        # Presence of prepaidBalance / onDemandUsed / onDemandCap marks the new shape.
        $has141 = $false
        foreach ($k in @('prepaidBalance', 'onDemandUsed', 'onDemandCap', 'isUnifiedBillingUser')) {
            if ($null -ne $cfg.PSObject.Properties[$k]) { $has141 = $true; break }
        }
        if (-not $has141 -and -not $periodEnd) {
            # Old-shaped event missing usage and end → nothing useful.
            return $null
        }
        return [pscustomobject]@{
            remaining_pct = $null
            used_pct      = $null
            fetched_at    = $fetchedAt
            period_end    = $periodEnd
            source        = 'unified.jsonl:billing:grok-1.0.41-period'
            kind          = 'weekly'
            format        = 'grok-1.0.41'
        }
    }
    catch { return $null }
}

function Get-BobCursorOverspendState {
    # none | over (on-demand spend > 0) | at-limit (spend reached the limit) | unknown (no spend data)
    param($UsedCents, $LimitCents, $OverageGbp, $OverageUsd)
    $c = $null
    if ($null -ne $UsedCents -and [string]$UsedCents -ne '') { try { $c = [double]$UsedCents } catch { } }
    if ($null -eq $c -and $null -ne $OverageUsd -and [string]$OverageUsd -ne '') { try { $c = [double]$OverageUsd * 100.0 } catch { } }
    if ($null -eq $c -and $null -ne $OverageGbp -and [string]$OverageGbp -ne '') { try { $c = [double]$OverageGbp * 100.0 } catch { } }
    if ($null -eq $c) { return 'unknown' }
    if ($c -le 0) { return 'none' }
    if ($null -ne $LimitCents -and [string]$LimitCents -ne '') {
        try { if ([double]$LimitCents -gt 0 -and $c -ge [double]$LimitCents) { return 'at-limit' } } catch { }
    }
    return 'over'
}

function Get-BobTrayDigestMachineSummary {
    # Digest machines.<id> -> grok pools (grok-weekly/grok-chat with period_end), cursor pools and overspend.
    param($Digest, [string]$MachineId)
    $r = [pscustomobject]@{ grok_pools = @(); cursor_pools = @(); overspend_gbp = $null; overspend_state = $null }
    if (-not $Digest -or -not $Digest.machines -or -not $MachineId) { return $r }
    $ent = $null
    foreach ($p in @($Digest.machines.PSObject.Properties)) {
        if ([string]$p.Name -ieq $MachineId) { $ent = $p.Value; break }
    }
    if (-not $ent) { return $r }
    $grok = @(); $cur = @()
    foreach ($row in @($ent.cursor_pools)) {
        if (-not $row) { continue }
        $rid = [string]$row.id
        if (-not $rid) { $rid = [string]$row.group_id }
        $rem = $row.remaining
        if ($null -eq $rem) { $rem = $row.remaining_pct }
        $item = [pscustomobject]@{ id = $rid; label = $(if ($row.label) { [string]$row.label } else { $rid }); remaining_pct = $rem; period_end = $(if ($row.period_end) { [string]$row.period_end } else { $null }) }
        if ($rid -in @('grok-weekly', 'grok-chat', 'sand')) { $grok += ,$item } else { $cur += ,$item }
    }
    $r.grok_pools = $grok
    $r.cursor_pools = $cur
    if ($null -ne $ent.overage_gbp -and [string]$ent.overage_gbp -ne '') { try { $r.overspend_gbp = [double]$ent.overage_gbp } catch { } }
    if ($ent.overspend_state) { $r.overspend_state = [string]$ent.overspend_state }
    return $r
}

function ConvertTo-BobCursorUsageDoc {
    param($j)
    if (-not $j) { return $null }
    $remain = $null
    $used = $null
    $overGbp = $null
    $overUsd = $null
    $cents = $null
    # remaining_pct / used_pct are Spending Cursor Models (not Sand).
    if ($null -ne $j.remaining_pct -and [string]$j.remaining_pct -ne '') {
        $remain = [int]$j.remaining_pct
    }
    if ($null -ne $j.used_pct -and [string]$j.used_pct -ne '') { $used = [double]$j.used_pct }
    if ($null -eq $used) {
        if ($null -ne $j.percentUsed) { $used = [double]$j.percentUsed }
        elseif ($null -ne $j.creditUsagePercent) { $used = [double]$j.creditUsagePercent }
    }
    if ($null -eq $remain -and $null -ne $used) {
        $remain = [int][math]::Round(100.0 - [double]$used)
    }
    # Legacy: usagePercent without used_pct was Sand — do not map to Cursor Models remaining.
    if ($null -ne $j.overage_gbp -and [string]$j.overage_gbp -ne '') { $overGbp = [double]$j.overage_gbp }
    if ($null -ne $j.overage_usd -and [string]$j.overage_usd -ne '') { $overUsd = [double]$j.overage_usd }
    if ($null -ne $j.on_demand_used_cents -and [string]$j.on_demand_used_cents -ne '') { $cents = [int]$j.on_demand_used_cents }
    $odLimit = $null
    $odRemain = $null
    $odUsedPct = $null
    if ($null -ne $j.on_demand_limit_cents -and [string]$j.on_demand_limit_cents -ne '') {
        try { $odLimit = [int]$j.on_demand_limit_cents } catch { }
    }
    if ($null -ne $j.on_demand_remaining_pct -and [string]$j.on_demand_remaining_pct -ne '') {
        try { $odRemain = [int]$j.on_demand_remaining_pct } catch { }
    }
    if ($null -ne $j.on_demand_used_pct -and [string]$j.on_demand_used_pct -ne '') {
        try { $odUsedPct = [int]$j.on_demand_used_pct } catch { }
    }
    if ($null -eq $remain -and $null -eq $used -and $null -eq $overGbp -and $null -eq $overUsd -and $null -eq $odRemain) { return $null }
    if ($null -ne $remain) {
        if ($remain -lt 0) { $remain = 0 }
        if ($remain -gt 100) { $remain = 100 }
    }
    if ($null -eq $used -and $null -ne $remain) { $used = 100 - $remain }
    $periodEnd = $null
    if ($j.period_end) { $periodEnd = [string]$j.period_end }
    $sandUsed = $null
    $sandRemain = $null
    $sandExhausted = $null
    $sandPeriodEnd = $null
    if ($null -ne $j.sand_used_pct -and [string]$j.sand_used_pct -ne '') { $sandUsed = [int]$j.sand_used_pct }
    if ($null -ne $j.sand_remaining_pct -and [string]$j.sand_remaining_pct -ne '') { $sandRemain = [int]$j.sand_remaining_pct }
    if ($null -ne $j.sand_exhausted -and [string]$j.sand_exhausted -ne '') {
        try { $sandExhausted = [bool]$j.sand_exhausted } catch { $sandExhausted = $null }
    }
    if ($j.sand_period_end) { $sandPeriodEnd = [string]$j.sand_period_end }
    $spendGroups = @()
    if ($j.cursor_spending_groups) {
        foreach ($g in @($j.cursor_spending_groups)) {
            if (-not $g) { continue }
            $spendGroups += ,[pscustomobject]@{
                id             = $(if ($g.id) { [string]$g.id } else { $null })
                label          = $(if ($g.label) { [string]$g.label } else { $null })
                used_pct       = $(if ($null -ne $g.used_pct -and [string]$g.used_pct -ne '') { [int]$g.used_pct } else { $null })
                remaining_pct  = $(if ($null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') { [int]$g.remaining_pct } else { $null })
                source         = $(if ($g.source) { [string]$g.source } else { $null })
            }
        }
    }
    return [pscustomobject]@{
        remaining_pct = $(if ($null -eq $remain) { $null } else { [int]$remain })
        used_pct      = $(if ($null -eq $used) { $null } else { [int][math]::Round([double]$used) })
        cursor_spending_groups = @($spendGroups)
        overage_gbp   = $overGbp
        overage_usd   = $overUsd
        on_demand_used_cents = $cents
        on_demand_limit_cents = $odLimit
        on_demand_remaining_pct = $odRemain
        on_demand_used_pct = $odUsedPct
        on_demand_enabled = $(if ($null -ne $j.on_demand_enabled -and [string]$j.on_demand_enabled -ne '') { [bool]$j.on_demand_enabled } else { $null })
        bonus_spend_cents = $(if ($null -ne $j.bonus_spend_cents -and [string]$j.bonus_spend_cents -ne '') { [int]$j.bonus_spend_cents } else { $null })
        remaining_bonus = $(if ($null -ne $j.remaining_bonus -and [string]$j.remaining_bonus -ne '') { [bool]$j.remaining_bonus } else { $null })
        bonus_tooltip = $(if ($j.bonus_tooltip) { [string]$j.bonus_tooltip } else { $null })
        overage_source = $(if ($j.overage_source) { [string]$j.overage_source } else { $null })
        overspend_state = $(if ($j.overspend_state) { [string]$j.overspend_state } else { (Get-BobCursorOverspendState -UsedCents $cents -LimitCents $odLimit -OverageGbp $overGbp -OverageUsd $overUsd) })
        period_end    = $periodEnd
        sand_used_pct = $sandUsed
        sand_remaining_pct = $sandRemain
        sand_exhausted = $sandExhausted
        sand_period_end = $sandPeriodEnd
        fetched_at    = $(if ($j.fetched_at) { [string]$j.fetched_at } elseif ($j.ts) { [string]$j.ts } else { $null })
        source        = 'cursor-agent'
        kind          = 'weekly'
    }
}

function ConvertTo-BobCursorSpendingPctPoints {
    param($Raw)
    if ($null -eq $Raw -or [string]$Raw -eq '') { return $null, $null }
    try {
        $usedF = [double]$Raw
        $usedI = [int][math]::Round($usedF)
        $remain = [int][math]::Round(100.0 - $usedF)
        return $usedI, $remain
    }
    catch { return $null, $null }
}

function ConvertTo-BobCursorSandPct {
    param($Raw)
    if ($null -eq $Raw -or [string]$Raw -eq '') { return $null, $null }
    try {
        $usedF = [double]$Raw
        if ($usedF -ge 0.0 -and $usedF -le 1.0) { $usedF = $usedF * 100.0 }
        $usedI = [int][math]::Round($usedF)
        $remain = [int][math]::Round(100.0 - $usedF)
        return $usedI, $remain
    }
    catch { return $null, $null }
}

function Get-BobCursorSpendingFromApiFixture {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path $Path)) { return $null }
    try {
        $fix = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch { return $null }
    $period = $fix.period
    $sand = $fix.sand
    $pu = $null
    if ($period -and $period.planUsage) { $pu = $period.planUsage }
    $autoUsed = $autoRemain = $apiUsed = $apiRemain = $null
    if ($pu) {
        $autoUsed, $autoRemain = ConvertTo-BobCursorSpendingPctPoints $pu.autoPercentUsed
        $apiUsed, $apiRemain = ConvertTo-BobCursorSpendingPctPoints $pu.apiPercentUsed
    }
    $sandUsed = $sandRemain = $null
    if ($sand) {
        $sandRaw = $sand.usagePercent
        if ($null -eq $sandRaw -or [string]$sandRaw -eq '') { $sandRaw = $sand.percentUsed }
        $sandUsed, $sandRemain = ConvertTo-BobCursorSandPct $sandRaw
    }
    $groups = @(
        [pscustomobject]@{ id = 'grok-chat'; label = 'grok chat'; used_pct = $sandUsed; remaining_pct = $sandRemain; source = 'GetSandUsageStatus.usagePercent' }
        [pscustomobject]@{ id = 'high-cost-models'; label = 'high cost models'; used_pct = $apiUsed; remaining_pct = $apiRemain; source = 'GetCurrentPeriodUsage.planUsage.apiPercentUsed' }
        [pscustomobject]@{ id = 'auto'; label = 'Low cost models'; used_pct = $autoUsed; remaining_pct = $autoRemain; source = 'GetCurrentPeriodUsage.planUsage.autoPercentUsed' }
    )
    $periodEnd = $null
    if ($period -and $period.billingCycleEnd) {
        $periodEnd = [string]$period.billingCycleEnd
        # Cursor sends epoch milliseconds; the digest/tray want ISO-8601 (same as Get-CursorAgentUsage.py).
        $ms = 0.0
        if ([double]::TryParse($periodEnd, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$ms) -and $ms -gt 10000000000) {
            $periodEnd = [DateTimeOffset]::FromUnixTimeMilliseconds([long]$ms).UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
    }
    $cents = $null
    $limitCents = $null
    if ($period -and $period.spendLimitUsage) {
        if ($null -ne $period.spendLimitUsage.individualUsed) {
            try { $cents = [int][math]::Round([double]$period.spendLimitUsage.individualUsed) } catch { }
        }
        if ($null -ne $period.spendLimitUsage.individualLimit) {
            try { $limitCents = [int][math]::Round([double]$period.spendLimitUsage.individualLimit) } catch { }
        }
    }
    $overageUsd = $overageGbp = $null
    if ($null -ne $cents) {
        $overageUsd = [math]::Round($cents / 100.0, 2)
        $rateEnv = [string]$env:BOB_CURSOR_USD_GBP_RATE
        if ($rateEnv) {
            try {
                $rate = [double]$rateEnv
                if ($rate -gt 0) { $overageGbp = [math]::Round($overageUsd * $rate, 2) }
            }
            catch { }
        }
    }
    $out = [ordered]@{
        ok                     = $true
        source                 = 'cursor-agent'
        kind                   = 'weekly'
        used_pct               = $autoUsed
        remaining_pct          = $autoRemain
        cursor_models_source   = 'GetCurrentPeriodUsage.planUsage.autoPercentUsed'
        sand_used_pct          = $sandUsed
        sand_remaining_pct     = $sandRemain
        cursor_spending_groups = @($groups)
    }
    if ($periodEnd) { $out.period_end = $periodEnd }
    if ($sandRemain -ne $null -and [int]$sandRemain -le 0) { $out.sand_exhausted = $true }
    if ($null -ne $overageUsd) {
        $out.overage_usd = $overageUsd
        $out.on_demand_used_cents = $cents
        $out.overage_source = 'period.spendLimitUsage.individualUsed'
    }
    if ($null -ne $limitCents) { $out.on_demand_limit_cents = $limitCents }
    if ($null -ne $overageGbp) { $out.overage_gbp = $overageGbp }
    if ($sand -and $sand.nextResetTimestampUtc) { $out.sand_period_end = [string]$sand.nextResetTimestampUtc }
    if ($fix.cursor_spending_groups) { $out.cursor_spending_groups = @($fix.cursor_spending_groups) }
    return [pscustomobject]$out
}

function Get-BobCursorAgentWeeklyRemaining {
    # Grok Bot / Cursor-agent account. Not Grok Build (xAI) unified.jsonl.
    $fixturePath = [string]$env:BOB_CURSOR_AGENT_FIXTURE
    if ($fixturePath -and (Test-Path $fixturePath)) {
        $fromFix = Get-BobCursorSpendingFromApiFixture -Path $fixturePath
        if ($fromFix) { return ConvertTo-BobCursorUsageDoc $fromFix }
    }
    if ($env:BOB_CURSOR_USAGE_FILE) {
        if (-not (Test-Path $env:BOB_CURSOR_USAGE_FILE)) { return $null }
        try {
            $j = Get-Content $env:BOB_CURSOR_USAGE_FILE -Raw -Encoding UTF8 | ConvertFrom-Json
            return ConvertTo-BobCursorUsageDoc $j
        }
        catch { return $null }
    }
    $cache = $null
    try { $cache = Join-Path (Get-BridgeRoot) 'cursor-agent-usage.json' } catch { }
    if ($cache -and (Test-Path $cache)) {
        try {
            $age = [datetime]::UtcNow - [IO.File]::GetLastWriteTimeUtc($cache)
            if ($age.TotalMinutes -lt 15) {
                $j = Get-Content $cache -Raw -Encoding UTF8 | ConvertFrom-Json
                $doc = ConvertTo-BobCursorUsageDoc $j
                if ($doc) { return $doc }
            }
        }
        catch { }
    }
    # #60: any machine. The fetcher ships with the tray (tools\Get-CursorAgentUsage.py) and python is
    # discovered (PATH, py launcher, Program Files, per-user, C:\Python*) - not just C:\Python\Python312.
    $py = Resolve-BobCursorPython
    $script = Resolve-BobCursorUsageScript
    $errPath = $null
    try { $errPath = Join-Path (Get-BridgeRoot) 'cursor-agent-usage.error.json' } catch { }
    if (-not $py -or -not $script) {
        $why = $(if (-not $script) { 'fetcher-script-missing' } else { 'python-missing' })
        if ($errPath) { try { Write-JsonFile $errPath ([pscustomobject]@{ ok = $false; error = $why; at = [DateTime]::UtcNow.ToString('o') }) } catch { } }
        return $null
    }
    try {
        $raw = (& $py $script 2>$null) -join "`n"
        $j = $raw | ConvertFrom-Json
        if ($j -and $j.ok -eq $false) {
            # Stage name only (token-missing, key-unprotect, cryptography-missing, http-401, network ...).
            if ($errPath) { try { Write-JsonFile $errPath ([pscustomobject]@{ ok = $false; error = [string]$j.error; detail = [string]$j.detail; at = [DateTime]::UtcNow.ToString('o') }) } catch { } }
            return $null
        }
        $doc = ConvertTo-BobCursorUsageDoc $j
        if ($doc -and $cache) {
            try { Write-JsonFile $cache $doc } catch { }
        }
        if ($errPath -and (Test-Path $errPath)) { try { Remove-Item -LiteralPath $errPath -Force } catch { } }
        if ($doc) { return $doc }
    }
    catch { }
    return $null
}

function Resolve-BobCursorPython {
    # First python.exe that exists. Skips the Microsoft Store stub (WindowsApps) which opens the Store.
    $cands = New-Object System.Collections.Generic.List[string]
    foreach ($e in @($env:BOB_CURSOR_PYTHON, $env:BOB_PYTHON)) { if ($e) { $cands.Add($e.Trim()) } }
    try {
        foreach ($cmd in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
            if ($cmd.Source -and $cmd.Source -notmatch '\\WindowsApps\\') { $cands.Add($cmd.Source) }
        }
    } catch { }
    try {
        $pyl = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pyl) {
            $exe = (& $pyl.Source -3 -c 'import sys;print(sys.executable)' 2>$null | Select-Object -First 1)
            if ($exe) { $cands.Add([string]$exe) }
        }
    } catch { }
    foreach ($ver in @('313', '312', '311', '310')) {
        $cands.Add("C:\Python\Python$ver\python.exe")
        $cands.Add("C:\Python$ver\python.exe")
        if ($env:ProgramFiles) { $cands.Add((Join-Path $env:ProgramFiles "Python$ver\python.exe")) }
        if ($env:LOCALAPPDATA) { $cands.Add((Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver\python.exe")) }
    }
    foreach ($c in $cands) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Resolve-BobCursorUsageScript {
    $rel = 'tools\Get-CursorAgentUsage.py'
    $roots = New-Object System.Collections.Generic.List[string]
    try { $roots.Add((Get-ModuleRoot)) } catch { }
    try { $roots.Add((Split-Path (Get-ModuleRoot) -Parent)) } catch { }
    foreach ($r in $roots) {
        if (-not $r) { continue }
        $cand = Join-Path $r $rel
        if (Test-Path -LiteralPath $cand) { return $cand }
    }
    return $null
}

function Test-BobTrayRemainingKnown {
    param($RemainingPct)
    if ($null -eq $RemainingPct) { return $false }
    if (($RemainingPct -is [string]) -and [string]::IsNullOrWhiteSpace([string]$RemainingPct)) { return $false }
    return $true
}

function Get-BobTrayBarFillRgb {
    param([int]$Pct)
    if ($Pct -lt 0) { $Pct = 0 }
    if ($Pct -gt 100) { $Pct = 100 }
    # 0 = red, 50 = amber, 100 = green.
    $red = @{ r = 248; g = 81; b = 73 }
    $amber = @{ r = 210; g = 153; b = 34 }
    $green = @{ r = 63; g = 185; b = 80 }
    if ($Pct -ge 50) {
        $t = ($Pct - 50) / 50.0
        $a = $amber; $b = $green
    }
    else {
        $t = $Pct / 50.0
        $a = $red; $b = $amber
    }
    return [pscustomobject]@{
        r = [int][math]::Round($a.r + ($b.r - $a.r) * $t)
        g = [int][math]::Round($a.g + ($b.g - $a.g) * $t)
        b = [int][math]::Round($a.b + ($b.b - $a.b) * $t)
    }
}

function Get-BobTrayBarPaint {
    [CmdletBinding()]
    param(
        $RemainingPct,
        [int]$BarWidth = 392
    )
    if (-not (Test-BobTrayRemainingKnown $RemainingPct)) {
        return [pscustomobject]@{
            remaining_pct = $null
            known         = $false
            show_track    = $false
            show_fill     = $false
            fill_width    = $null
            fill_r        = $null
            fill_g        = $null
            fill_b        = $null
            caption       = 'Weekly remaining  n/a'
            pulse         = $false
            kind          = 'unknown'
        }
    }
    $pct = [int]$RemainingPct
    if ($pct -lt 0) { $pct = 0 }
    if ($pct -gt 100) { $pct = 100 }
    $inner = [math]::Max(0, $BarWidth - 2)
    $w = [int]($inner * $pct / 100)
    if ($w -lt 8 -and $pct -gt 0) { $w = 8 }
    if ($pct -eq 0) { $w = 0 }
    $rgb = Get-BobTrayBarFillRgb -Pct $pct
    return [pscustomobject]@{
        remaining_pct = $pct
        known         = $true
        show_track    = $true
        show_fill     = ($w -gt 0)
        fill_width    = $w
        fill_r        = [int]$rgb.r
        fill_g        = [int]$rgb.g
        fill_b        = [int]$rgb.b
        caption       = ('Weekly remaining    {0}%' -f $pct)
        pulse         = ($pct -lt 10)
        kind          = 'weekly'
    }
}

function Get-BobTrayAlertKind {
    [CmdletBinding()]
    param(
        [string[]]$Alerts,
        $RemainingPct
    )
    foreach ($a in @($Alerts)) {
        if (-not $a) { continue }
        if ($a -match 'watcher_down') { return 'watcher' }
        if ($a -match 'agent_stall') { return 'stall' }
        if ($a -match 'ACTION_REQUIRED') { return 'stall' }
        if ($a -match '(?i)no_tokens|out of tokens|needs Simon') { return 'no_tokens' }
    }
    $paint = Get-BobTrayBarPaint -RemainingPct $RemainingPct
    if ($paint.pulse) { return 'weekly' }
    return 'none'
}


function Get-BobSeatConfig {
    $candidates = @()
    try { $candidates += (Join-Path (Get-ModuleRoot) 'config\bob-seats.json') } catch { }
    if ($env:BOB_SEATS_FILE) { $candidates = @($env:BOB_SEATS_FILE) + $candidates }
    foreach ($p in $candidates) {
        if (-not $p -or -not (Test-Path $p)) { continue }
        try {
            $j = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.seats) { return @($j.seats) }
        } catch { }
    }
    return @(
        [pscustomobject]@{ id = 'smart-catalogue'; label = 'Smart Catalogue'; email = 'social@smartcatalogue.uk'; machines = @('win-mpre8vi4u6u') },
        [pscustomobject]@{ id = 'club-madeira'; label = 'Club Madeira'; email = 'social@clubmadeira.uk'; machines = @('flamingo') },
        [pscustomobject]@{ id = 'ntsa'; label = 'ntsa'; email = 'si@ntsa.uk'; machines = @('marchhare', 'ce-priority-dev1') }
    )
}

function Get-BobSeatForMachine {
    param([string]$MachineId)
    $mid = [string]$MachineId
    if (-not $mid) { return $null }
    $mid = $mid.ToLowerInvariant()
    foreach ($s in @(Get-BobSeatConfig)) {
        foreach ($m in @($s.machines)) {
            if ([string]$m -and [string]$m.ToLowerInvariant() -eq $mid) { return $s }
        }
    }
    return $null
}

function Get-BobCursorOverageGbp {
    # CAST IRON (agentic_build #423 / AgentMonitor #150 / Simon 2026-09-27): TipForm
    # Cursor overspend is LOCAL only. Read spendLimitUsage via
    # Get-BobCursorAgentWeeklyRemaining / Get-CursorAgentUsage.py.
    # Never digest GET, never cursor_pools / seat-cache peer GBP labels.
    # Digest may still *publish* overage_gbp for other seats; this getter must not consume it.
    # Never treat tip_cursor.json as pounds.
    try {
        $doc = Get-BobCursorAgentWeeklyRemaining
        if ($doc -and $null -ne $doc.overage_gbp -and [string]$doc.overage_gbp -ne '') {
            return [double]$doc.overage_gbp
        }
    } catch { }
    return $null
}
function Test-BobCursorOverageLabel {
    param([string]$Label)
    if (-not $Label) { return $false }
    return ($Label -match '^-') -or ($Label -match [char]0x00A3)
}

function Format-BobCursorAccountLabel {
    param($RemainingPct, $UsedPct)
    if ($null -ne $RemainingPct -and [string]$RemainingPct -ne '') {
        return ('{0}%' -f [int]$RemainingPct)
    }
    $gbp = Get-BobCursorOverageGbp
    if ($null -ne $gbp) {
        return ('-{0}{1:N2}' -f [char]0x00A3, [math]::Abs([double]$gbp))
    }
    if ($null -ne $UsedPct -and [double]$UsedPct -gt 100) {
        # no money figure — fall back only if tip missing
        return ('over +{0}%' -f [int][math]::Round([double]$UsedPct - 100.0))
    }
    return 'empty'
}



function ConvertTo-BobUtcDateTime {
    param($Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    try {
        $raw = [string]$Value
        if ($raw -match '^\d{12,}$') {
            return [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$raw).UtcDateTime
        }
        if ($raw -match '^\d{10}$') {
            return [DateTimeOffset]::FromUnixTimeSeconds([int64]$raw).UtcDateTime
        }
        $dt = [datetime]::Parse($raw, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
        if ($dt.Kind -eq [DateTimeKind]::Unspecified) { $dt = [DateTime]::SpecifyKind($dt, [DateTimeKind]::Utc) }
        return $dt.ToUniversalTime()
    }
    catch { return $null }
}

function Format-BobResetCountdownPart {
    param([int]$Value, [string]$Singular, [string]$Plural)
    if ($Value -le 0) { return $null }
    $word = if ($Value -eq 1) { $Singular } else { $Plural }
    return ('{0} {1}' -f $Value, $word)
}

function Format-BobResetLabel {
    <#
    .SYNOPSIS
      TipForm reset line: countdown until period_end (AgentMonitor #148 / FR #445).
    .NOTES
      Hide when FetchedAt >= PeriodEnd (polled since reset). Clamp negative span to zero.
      FR #445: no "Until reset:" prefix. Units:
        days > 0  -> days + hours (no minutes)
        days = 0  -> hours + minutes (no days)
      No polling here - format only from known timestamps.
    #>
    param(
        $PeriodEnd,
        $FetchedAt = $null,
        $Now = $null
    )
    if (-not $PeriodEnd -or [string]::IsNullOrWhiteSpace([string]$PeriodEnd)) { return $null }
    try {
        $dt = ConvertTo-BobUtcDateTime $PeriodEnd
        if (-not $dt) { return $null }
        $fetchedUtc = ConvertTo-BobUtcDateTime $FetchedAt
        # Polled since reset: fetch landed at/after the reset instant → hide line.
        if ($null -ne $fetchedUtc -and $fetchedUtc -ge $dt) { return $null }
        $nowUtc = ConvertTo-BobUtcDateTime $Now
        if (-not $nowUtc) { $nowUtc = [DateTime]::UtcNow }
        $span = $dt - $nowUtc
        # Period already over: the figure is stale/unknown - hide it, do not clamp to "0 minutes".
        if ($span -le [TimeSpan]::Zero) { return $null }
        $days = [int][math]::Floor($span.TotalDays)
        $hours = [int]$span.Hours
        $mins = [int]$span.Minutes
        $parts = @()
        if ($days -ge 1) {
            $parts += ,(Format-BobResetCountdownPart -Value $days -Singular 'day' -Plural 'days')
            $hPart = Format-BobResetCountdownPart -Value $hours -Singular 'hour' -Plural 'hours'
            if ($hPart) { $parts += ,$hPart }
            return (($parts | Where-Object { $_ }) -join ', ')
        }
        $hPart = Format-BobResetCountdownPart -Value $hours -Singular 'hour' -Plural 'hours'
        if ($hPart) { $parts += ,$hPart }
        $mPart = Format-BobResetCountdownPart -Value $mins -Singular 'minute' -Plural 'minutes'
        if ($mPart) { $parts += ,$mPart }
        if ($parts.Count -eq 0) { return '0 minutes' }
        return ($parts -join ', ')
    }
    catch { return $null }
}

function Test-BobPeriodExpired {
    # True when period_end is known and already past: the usage figure that goes with it is stale.
    param($PeriodEnd, $Now = $null)
    $dt = ConvertTo-BobUtcDateTime $PeriodEnd
    if (-not $dt) { return $false }
    $nowUtc = ConvertTo-BobUtcDateTime $Now
    if (-not $nowUtc) { $nowUtc = [DateTime]::UtcNow }
    return ($dt -le $nowUtc)
}

function Resolve-BobTrayLivePeriod {
    # Weekly pct + period_end for a Grok account row. A past period_end => both unknown (null), so
    # the tray hides them instead of showing n/a / a stale reset date.
    param($Pct, $PeriodEnd, $FetchedAt = $null, $Now = $null)
    $pctOut = $Pct
    $endOut = $null
    if ($PeriodEnd -and -not [string]::IsNullOrWhiteSpace([string]$PeriodEnd)) { $endOut = [string]$PeriodEnd }
    if ($endOut -and (Test-BobPeriodExpired -PeriodEnd $endOut -Now $Now)) {
        $pctOut = $null
        $endOut = $null
    }
    $label = $null
    if ($endOut) { $label = Format-BobResetLabel -PeriodEnd $endOut -FetchedAt $FetchedAt -Now $Now }
    return [pscustomobject]@{ pct = $pctOut; period_end = $endOut; reset_label = $label }
}

function Format-BobTrayWorkerLine {
    # "{irc nick}: {work|offered:<work>|idle}" - FR #663: offered is not doing.
    param($Worker)
    if (-not $Worker) { return $null }
    $nick = ([string]$Worker.nick).Trim()
    if (-not $nick) { return $null }
    $state = ([string]$Worker.state).Trim().ToLowerInvariant()
    $text = 'idle'
    if ($state -eq 'doing') {
        $w = ([string]$Worker.work) -replace '[\r\n\t]+', ' '
        $w = $w.Trim()
        if (-not $w) { $w = 'working' }
        $text = $w
    }
    elseif ($state -eq 'offered') {
        $w = ([string]$Worker.work) -replace '[\r\n\t]+', ' '
        $w = $w.Trim()
        if ($w -and $w -ne 'offered') { $text = ('offered: {0}' -f $w) }
        else { $text = 'offered' }
    }
    return ('{0}: {1}' -f $nick, $text)
}

function Get-BobTrayDigestWorkers {
    # Digest machines.<id>.workers = [{nick,state,work,updated}] (Jeeves-maintained) -> tile worker rows.
    param($Digest, [string]$MachineId)
    if (-not $Digest -or -not $Digest.machines -or -not $MachineId) { return @() }
    $ent = $null
    foreach ($p in @($Digest.machines.PSObject.Properties)) {
        if ([string]$p.Name -ieq $MachineId) { $ent = $p.Value; break }
    }
    if (-not $ent -or -not ($ent.PSObject.Properties.Name -contains 'workers')) { return @() }
    $out = @()
    foreach ($w in @($ent.workers)) {
        if (-not $w -or -not ($w.PSObject.Properties.Name -contains 'nick')) { continue }
        $st = ([string]$w.state).Trim().ToLowerInvariant()
        if ($st -ne 'doing' -and $st -ne 'idle' -and $st -ne 'offered') { continue }
        $out += ,[pscustomobject]@{ nick = [string]$w.nick; state = $st; work = [string]$w.work; updated = [string]$w.updated }
    }
    return @($out | Sort-Object -Property nick)
}

function Get-BobTrayTitle {
    param($MachineId)
    $mid = [string]$MachineId
    if (-not $mid) {
        try { $mid = Get-ThisMachineId } catch { }
    }
    if (-not $mid -and $env:BOB_MACHINE_ID) { $mid = [string]$env:BOB_MACHINE_ID }
    if (-not $mid) { $mid = 'this-machine' }
    return ('#Bobiverse ({0})' -f $mid)
}

function Get-BobLiveGrokAgents {
    # grok.exe on this box, including sessions Bob did not start. Not Grok Bot.exe.
    if ($env:BOB_SKIP_LIVE_GROK -eq '1') { return @() }
    $byPid = @{}
    $sessPath = Join-Path $env:USERPROFILE '.grok\active_sessions.json'
    if (Test-Path $sessPath) {
        try {
            foreach ($s in @(Get-Content $sessPath -Raw -Encoding UTF8 | ConvertFrom-Json)) {
                if (-not $s.pid) { continue }
                $byPid[[int]$s.pid] = $s
            }
        }
        catch { }
    }
    $out = @()
    $procs = @()
    try {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                $_.Name -eq 'grok.exe' -or ($_.ExecutablePath -and $_.ExecutablePath -match '[\\/]grok\.exe$')
            })
    }
    catch { return @() }
    foreach ($p in $procs) {
        $cmd = [string]$p.CommandLine
        if ($cmd -match '--type=') { continue }
        if ([string]$p.Name -match 'Grok Bot') { continue }
        $pid = [int]$p.ProcessId
        $meta = $null
        if ($byPid.ContainsKey($pid)) { $meta = $byPid[$pid] }
        $cwd = $null
        $sid = ('grok-' + $pid)
        $opened = $null
        if ($meta) {
            if ($meta.cwd) { $cwd = [string]$meta.cwd }
            if ($meta.session_id) { $sid = [string]$meta.session_id }
            if ($meta.opened_at) { $opened = [string]$meta.opened_at }
        }
        if (-not $opened -and $p.CreationDate) {
            try { $opened = [Management.ManagementDateTimeConverter]::ToDateTime($p.CreationDate).ToUniversalTime().ToString('o') } catch { }
        }
        $out += ,[pscustomobject]@{
            id        = $sid
            sessionId = $sid
            pid       = $pid
            cwd       = $cwd
            claimedAt = $opened
            machine   = $null
            state     = 'running'
            source    = 'live-grok'
        }
    }
    return $out
}

function Get-BobTrayRepoLabel {
    param($Job, [switch]$SkipGit)
    if ($Job -and $Job.repo) {
        $r = [string]$Job.repo
        if ($r -and $r.Trim() -and $r.Trim() -ne '?' -and -not (Test-BobTrayLooksLikeSha $r)) {
            return $r.Trim()
        }
    }
    $cwd = $null
    if ($Job) { $cwd = [string]$Job.cwd }
    if (-not $SkipGit -and $cwd) {
        $slug = Get-GitHubSlugFromCwd $cwd
        if ($slug -and $slug -ne '?' -and -not (Test-BobTrayLooksLikeSha $slug)) { return $slug }
    }
    if ($cwd) {
        try {
            $leaf = Split-Path $cwd -Leaf
            if ($leaf -and -not (Test-BobTrayLooksLikeSha $leaf)) { return $leaf }
        }
        catch { }
    }
    return '?'
}

function Get-BobJobTrayFields {
    param($Job, [switch]$SkipGit)
    if (-not $Job) { return $null }
    $repo = Get-BobTrayRepoLabel -Job $Job -SkipGit:$SkipGit
    if ($repo -eq '?' -or (Test-BobTrayLooksLikeSha $repo)) { $repo = $null }
    $sha = $null
    if ($Job.sha) { $sha = [string]$Job.sha.Trim() }
    elseif (-not $SkipGit -and $Job.cwd) {
        try { $sha = Get-BobGitShortSha ([string]$Job.cwd) } catch { }
    }
    $model = $null
    if ($Job.model) { $model = [string]$Job.model }
    else {
        try { $model = Get-BobIrcModelFromJob $Job } catch { }
    }
    $desc = $null
    if ($Job.description) { $desc = [string]$Job.description }
    elseif ($Job.task) { $desc = [string]$Job.task }
    elseif ($Job.goal) {
        $g = [string]$Job.goal
        if ($g.Length -gt 48) { $g = $g.Substring(0, 45) + '...' }
        $desc = $g
    }
    $runTime = $null
    if ($Job.run_time) { $runTime = [string]$Job.run_time }
    else {
        $when = $Job.claimedAt
        if (-not $when) { $when = $Job.createdAt }
        $age = Get-BobJobAge $when
        if ($age -and $age -ne '?') { $runTime = $age }
    }
    return [pscustomobject]@{
        repo        = $repo
        sha         = $sha
        model       = $model
        description = $desc
        run_time    = $runTime
    }
}

function Format-BobTrayJobLine {
    param($Job, [switch]$SkipGit)
    if (-not $Job) { return $null }
    $f = Get-BobJobTrayFields -Job $Job -SkipGit:$SkipGit
    if (-not $f) { return $null }
    if (-not $f.repo -and -not $f.sha) { return $null }
    $st = [string]$Job.state
    if (-not $st) { $st = 'running' }
    if ($st -eq 'running') { $st = 'START' }
    elseif ($st -eq 'queued') { $st = 'QUEUED' }
    elseif ($st -eq 'stopped' -or $st -eq 'done' -or $st -eq 'complete') { $st = 'STOP' }
    else { $st = $st.ToUpperInvariant() }
    $parts = @($st)
    if ($f.repo) { $parts += $f.repo }
    if ($f.sha) { $parts += $f.sha }
    if ($f.model) { $parts += $f.model }
    if ($f.description) { $parts += $f.description }
    if ($f.run_time) { $parts += $f.run_time }
    return ($parts -join '  ')
}

function ConvertTo-BobTrayIntOrNull {
    param($Value)
    if ($null -eq $Value) { return $null }
    if (($Value -is [string]) -and [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    try { return [int]$Value } catch { return $null }
}

function Get-BobCursorSpendingGroupCatalog {
    return @(
        [pscustomobject]@{ id = 'grok-chat'; label = 'grok chat'; pcent_source = 'grok-chat' }
        [pscustomobject]@{ id = 'high-cost-models'; label = 'high cost models'; pcent_source = 'high-cost-models' }
        # Auto model picker → planUsage.autoPercentUsed (Cursor Models / autoBucketModels).
        # TipForm label FR #448: "Low cost models" (id stays auto for wire/cache compat).
        # Not on-demand. Legacy id low-cost-models still accepted in remain lookups.
        [pscustomobject]@{ id = 'auto'; label = 'Low cost models'; pcent_source = 'cursor-models' }
    )
}

function Get-BobTrayCursorGroupHelpTooltip {
    param([string]$GroupId)
    switch -Regex ($GroupId) {
        '^(grok-chat|grok.chat|sand)$' {
            return @'
grok chat (Cursor Sand / Grok Bot pool)
Included: Grok Bot desktop turns (Temporal sand). Fuel for grok-bot only — not MRB/PR builds.
Source: GetSandUsageStatus.usagePercent (remaining = 100 − used). 0% means exhausted, not unknown.
'@.Trim()
        }
        '^(high-cost-models|high.cost|other-models)$' {
            return @'
high cost models (named / Other Models / API tier)
Included: specific third-party / premium API models on planUsage.apiPercentUsed.
Not the Auto meter. 0% means this bar is empty, not n/a.
'@.Trim()
        }
        '^(auto|low-cost-models|low.cost|cursor-models)$' {
            return @'
Low cost models (Auto model / Cursor Models pool)
When the model picker is Auto, requests draw from this meter (planUsage.autoPercentUsed).
autoBucketModels includes default (Auto), Composer, Grok, Vega, etc. Docs: Auto bills at the
routed model's list price and uses the Cursor Models pool (Other Models only if the router
picks third-party). This is the cursor-models MRB/PR fuel gate. Not on-demand.
'@.Trim()
        }
        default {
            return @'
Cursor spending group. Hover a named bar (grok chat / high cost / Low cost models) for that quota.
0% is a real remaining value - never shown as n/a.
'@.Trim()
        }
    }
}

function Get-BobCursorGroupRemainFromLocalDoc {
    param($LocalCursorDoc, [string]$GroupId)
    if (-not $LocalCursorDoc) { return $null }
    $want = [string]$GroupId
    if ($want -eq 'low-cost-models' -or $want -eq 'cursor-models') { $want = 'auto' }
    # FR #445: grok-chat = Sand only — never Cursor remaining_pct / auto / high-cost.
    if ($want -eq 'grok-chat') {
        foreach ($g in @($LocalCursorDoc.cursor_spending_groups)) {
            if (-not $g) { continue }
            if ([string]$g.id -ne 'grok-chat') { continue }
            if ($null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') {
                return [int]$g.remaining_pct
            }
        }
        if ($null -ne $LocalCursorDoc.sand_remaining_pct -and [string]$LocalCursorDoc.sand_remaining_pct -ne '') {
            return [int]$LocalCursorDoc.sand_remaining_pct
        }
        return $null
    }
    foreach ($g in @($LocalCursorDoc.cursor_spending_groups)) {
        if (-not $g) { continue }
        $gid = [string]$g.id
        if ($gid -eq 'low-cost-models' -or $gid -eq 'cursor-models') { $gid = 'auto' }
        if ($gid -eq 'grok-chat') { continue }
        if ($gid -ne $want) { continue }
        if ($null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') {
            return [int]$g.remaining_pct
        }
    }
    if ($want -eq 'auto' -and $null -ne $LocalCursorDoc.remaining_pct) {
        return [int]$LocalCursorDoc.remaining_pct
    }
    return $null
}

function Get-BobCursorGroupRemainFromSeatCache {
    param($SeatCacheEntry, [string]$GroupId)
    if (-not $SeatCacheEntry) { return $null }
    if ($SeatCacheEntry.groups) {
        $g = $SeatCacheEntry.groups.$GroupId
        if ($g -and $null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') {
            try { return [int]$g.remaining_pct } catch { }
        }
    }
    if (($GroupId -eq 'low-cost-models' -or $GroupId -eq 'auto') -and $null -ne $SeatCacheEntry.remaining_pct -and [string]$SeatCacheEntry.remaining_pct -ne '') {
        try { return [int]$SeatCacheEntry.remaining_pct } catch { }
    }
    if ($SeatCacheEntry.groups -and $GroupId -eq 'auto' -and -not $SeatCacheEntry.groups.auto) {
        $g = $SeatCacheEntry.groups.'low-cost-models'
        if ($g -and $null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') {
            try { return [int]$g.remaining_pct } catch { }
        }
    }
    return $null
}

function Test-BobTrayWorkerNickKey {
    # Shop seat nick grammar: {machine}-{pid} (FR #357 / gh-Jeeves workers map).
    param([string]$Key)
    return ([string]$Key -match '^[A-Za-z0-9_]+-\d+$')
}

function Get-BobTrayWorkersFromNickMap {
    # Jeeves digest: workers is an object keyed by nick → {state,job,ts} (not an array).
    param($WorkersNode, [string]$MachineIdFilter = '')
    $out = @()
    if (-not $WorkersNode) { return $out }

    $isNickMap = $false
    if ($WorkersNode -is [pscustomobject] -or $WorkersNode -is [System.Collections.IDictionary]) {
        foreach ($prop in @($WorkersNode.PSObject.Properties)) {
            if (Test-BobTrayWorkerNickKey ([string]$prop.Name)) { $isNickMap = $true; break }
        }
    }
    function Resolve-BobTraySeatMachineId {
        param([string]$Nick, [string]$Filter)
        $nickMachine = $null
        if ($Nick -match '^([A-Za-z0-9_]+)-\d+$') {
            $nickMachine = [string]$Matches[1]
        }
        if ($Filter) {
            if ($nickMachine -and ($nickMachine.ToLowerInvariant() -ne $Filter.ToLowerInvariant())) {
                return $null
            }
            return $Filter
        }
        if ($nickMachine) { return $nickMachine }
        $mac = Resolve-BobiverseMachineFromIrcNick $Nick
        # Ignore bogus ids equal to the full nick (empty nicks{} Resolve-BobiverseMachineId passthrough).
        if ($mac -and $mac -ne $Nick) { return $mac }
        return $null
    }

    if ($isNickMap) {
        foreach ($prop in @($WorkersNode.PSObject.Properties)) {
            $nick = [string]$prop.Name
            if (-not (Test-BobTrayWorkerNickKey $nick)) { continue }
            $mac = Resolve-BobTraySeatMachineId -Nick $nick -Filter $MachineIdFilter
            if (-not $mac) { continue }
            $val = $prop.Value
            $state = 'idle'
            $job = ''
            if ($val -is [pscustomobject] -or $val -is [System.Collections.IDictionary]) {
                if ($val.state) { $state = [string]$val.state }
                if ($val.job) { $job = [string]$val.job }
                elseif ($val.working_on) { $job = [string]$val.working_on }
            }
            elseif ($null -ne $val -and [string]$val -ne '') {
                $job = [string]$val
            }
            $out += ,[pscustomobject]@{
                nick    = $nick
                machine = $mac
                state   = $state
                job     = $job
            }
        }
        return $out
    }

    # Legacy: array of nick strings or objects with .nick
    foreach ($wn in @($WorkersNode)) {
        if (-not $wn) { continue }
        $nick = [string]$wn
        $state = 'idle'
        $job = ''
        if ($wn -is [pscustomobject] -or $wn -is [System.Collections.IDictionary]) {
            if ($wn.nick) { $nick = [string]$wn.nick }
            elseif ($wn.id) { $nick = [string]$wn.id }
            if ($wn.state) { $state = [string]$wn.state }
            if ($wn.job) { $job = [string]$wn.job }
            elseif ($wn.working_on) { $job = [string]$wn.working_on }
        }
        if (-not (Test-BobTrayWorkerNickKey $nick)) { continue }
        $mac = Resolve-BobTraySeatMachineId -Nick $nick -Filter $MachineIdFilter
        if (-not $mac) { continue }
        $out += ,[pscustomobject]@{
            nick    = $nick
            machine = $mac
            state   = $state
            job     = $job
        }
    }
    return $out
}

function Add-BobTrayWorkersToMachineMap {
    param([hashtable]$WorkersByMachine, [object[]]$Seats)
    foreach ($seat in @($Seats)) {
        if (-not $seat) { continue }
        $mid = [string]$seat.machine
        if (-not $mid) { continue }
        if (-not $WorkersByMachine.ContainsKey($mid)) {
            $WorkersByMachine[$mid] = [pscustomobject]@{ seats = @() }
        }
        $cur = $WorkersByMachine[$mid]
        $list = @()
        if ($cur.seats) { $list = @($cur.seats) }
        # Dedupe by nick (machine-level wins if already present).
        $nick = [string]$seat.nick
        $already = $false
        foreach ($s in $list) {
            if ([string]$s.nick -eq $nick) { $already = $true; break }
        }
        if ($already) { continue }
        $list += ,$seat
        $WorkersByMachine[$mid] = [pscustomobject]@{ seats = $list }
    }
}

function New-BobTrayIrcWorkerJobRow {
    # FR #357: seat rows show "<STATE> <job>"; moot ear fallback is "ear online" (not START).
    param(
        [string]$MachineId,
        [string]$Description,
        [string]$Nick,
        [string]$State = 'ear online'
    )
    $stRaw = ([string]$State).Trim()
    if (-not $stRaw) { $stRaw = 'ear online' }
    $desc = ([string]$Description).Trim()
    if ($stRaw -eq 'ear online') {
        $line = 'ear online'
        $desc = 'ear online'
    }
    else {
        $stShow = $stRaw.ToUpperInvariant()
        if (-not $desc) { $desc = if ($Nick) { [string]$Nick } else { 'irc agent' } }
        $line = ('{0} {1}' -f $stShow, $desc).Trim()
    }
    $model = 'irc'
    if ($Nick) { $model = [string]$Nick }
    return [pscustomobject]@{
        id                    = ('irc-worker-' + $MachineId + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
        id8                   = 'irc'
        machine               = $MachineId
        repo                  = 'irc'
        sha                   = $null
        model                 = $model
        description           = $desc
        run_time              = $null
        duration              = $null
        state                 = $stRaw
        line                  = $line
        cwd                   = $null
        context_remaining_pct = $null
    }
}

function Expand-BobReportDigestView {
    param($Digest)
    $tasksByMachine = @{}
    $uptimeByMachine = @{}
    $pcentRows = @()
    $weeklyRows = @()
    $workersByMachine = @{}
    if (-not $Digest) {
        return [pscustomobject]@{
            tasksByMachine   = $tasksByMachine
            uptimeByMachine  = $uptimeByMachine
            pcentRows        = $pcentRows
            weeklyRows       = $weeklyRows
            workersByMachine = $workersByMachine
        }
    }

    $machineNodes = @()
    if ($Digest.machines) {
        foreach ($prop in @($Digest.machines.PSObject.Properties)) {
            $machineNodes += ,@{
                id   = [string]$prop.Name
                node = $prop.Value
            }
        }
    }

    if ($machineNodes.Count -gt 0) {
        foreach ($mn in $machineNodes) {
            $mid = Resolve-BobiverseMachineId ([string]$mn.id)
            if (-not $mid) { continue }
            $node = $mn.node
            if (-not $node) { continue }
            if ($node.task -and -not (Test-BobIrcDigestMachineReportsIdle $node)) {
                $task = $node.task
                if (-not $task.machine) {
                    $task = [pscustomobject]@{
                        machine     = $mid
                        repo        = $(if ($task.repo) { [string]$task.repo } else { $null })
                        sha         = $(if ($task.sha) { [string]$task.sha } else { $null })
                        model       = $(if ($task.model) { [string]$task.model } else { $null })
                        description = $(if ($task.description) { [string]$task.description } else { $null })
                        run_time    = $(if ($task.run_time) { [string]$task.run_time } else { $null })
                        state       = $(if ($task.state) { [string]$task.state } else { 'START' })
                    }
                }
                if (-not $tasksByMachine.ContainsKey($mid)) { $tasksByMachine[$mid] = @() }
                $tasksByMachine[$mid] += ,(ConvertFrom-BobReportDigestTask -Task $task -DefaultMachine $mid)
            }
            if ($node.uptime_since) {
                $uptimeByMachine[$mid] = [string]$node.uptime_since
            }
            # Digest weekly (xAI) — include 0 (#179).
            $weekPct = ConvertTo-BobTrayIntOrNull $node.weekly
            if ($null -ne $weekPct) {
                $weeklyRows += ,[pscustomobject]@{
                    machine = $mid
                    weekly  = $weekPct
                    period_end = $(if ($node.period_end) { [string]$node.period_end } elseif ($node.reset) { [string]$node.reset } else { $null })
                }
            }
            if ($node.pcent) {
                foreach ($pcProp in @($node.pcent.PSObject.Properties)) {
                    $src = [string]$pcProp.Name
                    if (-not $src) { continue }
                    $pct = ConvertTo-BobTrayIntOrNull $pcProp.Value
                    if ($null -eq $pct) { continue }
                    $pcentRows += ,[pscustomobject]@{
                        machine = $mid
                        source  = $src
                        pct     = $pct
                    }
                }
            }
            # FR #357: machines.<id>.workers is nick-keyed {state,job,ts}, not a count/array.
            $nodeNames = @($node.PSObject.Properties.Name)
            if ($nodeNames -contains 'workers' -and $null -ne $node.workers) {
                $seats = @(Get-BobTrayWorkersFromNickMap -WorkersNode $node.workers -MachineIdFilter $mid)
                if ($seats.Count -eq 0 -and $nodeNames -contains 'working_on' -and $node.working_on) {
                    # Legacy single working_on string with no nick map.
                    $seats = @(
                        [pscustomobject]@{
                            nick    = ''
                            machine = $mid
                            state   = 'busy'
                            job     = [string]$node.working_on
                        }
                    )
                }
                if ($seats.Count -gt 0) {
                    Add-BobTrayWorkersToMachineMap -WorkersByMachine $workersByMachine -Seats $seats
                }
            }
            elseif ($nodeNames -contains 'working_on' -and $node.working_on) {
                Add-BobTrayWorkersToMachineMap -WorkersByMachine $workersByMachine -Seats @(
                    [pscustomobject]@{
                        nick    = ''
                        machine = $mid
                        state   = 'busy'
                        job     = [string]$node.working_on
                    }
                )
            }
        }
    }
    else {
        foreach ($t in @($Digest.tasks)) {
            if (-not $t) { continue }
            $tm = [string]$t.machine
            if (-not $tm) { continue }
            $tm = Resolve-BobiverseMachineId $tm
            if (-not $tm) { continue }
            if (-not $tasksByMachine.ContainsKey($tm)) { $tasksByMachine[$tm] = @() }
            $tasksByMachine[$tm] += ,(ConvertFrom-BobReportDigestTask -Task $t -DefaultMachine $tm)
        }
        foreach ($u in @($Digest.uptime)) {
            if (-not $u) { continue }
            $um = [string]$u.machine
            if (-not $um) { continue }
            $um = Resolve-BobiverseMachineId $um
            if (-not $um) { continue }
            if ($u.since) { $uptimeByMachine[$um] = [string]$u.since }
        }
        foreach ($pc in @($Digest.pcent)) {
            if (-not $pc) { continue }
            $src = [string]$pc.source
            if (-not $src) { continue }
            $pct = ConvertTo-BobTrayIntOrNull $pc.pct
            if ($null -eq $pct) { continue }
            $pcentRows += ,[pscustomobject]@{
                machine = $(if ($pc.machine) { [string]$pc.machine } else { $null })
                source  = $src
                pct     = $pct
            }
        }
    }

    # Top-level workers{nick:{state,job}} — fill machines that lack seat rows (FR #357).
    if ($Digest.workers) {
        $topSeats = @(Get-BobTrayWorkersFromNickMap -WorkersNode $Digest.workers)
        Add-BobTrayWorkersToMachineMap -WorkersByMachine $workersByMachine -Seats $topSeats
    }

    return [pscustomobject]@{
        tasksByMachine   = $tasksByMachine
        uptimeByMachine  = $uptimeByMachine
        pcentRows        = $pcentRows
        weeklyRows       = $weeklyRows
        workersByMachine = $workersByMachine
    }
}

function Test-BobTrayDigestCodingTask {
    param($Task)
    if (-not $Task) { return $false }
    if ($Task.sha) { return $true }
    $repo = $null
    if ($Task.repo) { $repo = [string]$Task.repo }
    return (Test-BobIrcRepoOk $repo)
}

function ConvertFrom-BobReportDigestTask {
    param($Task, [string]$DefaultMachine)
    if (-not $Task) { return $null }
    if (-not (Test-BobTrayDigestCodingTask $Task)) { return $null }
    $mac = [string]$Task.machine
    if (-not $mac) { $mac = $DefaultMachine }
    $repo = $null
    if ($Task.repo) { $repo = [string]$Task.repo }
    $sha = $null
    if ($Task.sha) { $sha = [string]$Task.sha }
    $st = 'running'
    if ($Task.state) { $st = [string]$Task.state }
    return [pscustomobject]@{
        id          = $(if ($Task.id) { [string]$Task.id } else { ('digest-' + [guid]::NewGuid().ToString()) })
        machine     = $mac
        repo        = $repo
        sha         = $sha
        model       = $(if ($Task.model) { [string]$Task.model } else { $null })
        description = $(if ($Task.description) { [string]$Task.description } else { $null })
        run_time    = $(if ($Task.run_time) { [string]$Task.run_time } else { $null })
        state       = $st
        source      = 'report-digest'
    }
}

function Format-BobCursorControlPoolPctLabel {
    param($RemainingPct)
    if ($null -eq $RemainingPct) { return 'n/a' }
    return ('{0}%' -f [int]$RemainingPct)
}

function Format-BobCursorControlPoolHeading {
    param(
        [string]$GroupLabel,
        [string]$PctLabel,
        [string]$ResetLabel
    )
    # TipForm: "Cursor Models  0% [middle dot] 15 days, 2 hours" (FR #445). Missing reset -> n/a.
    $reset = if ($ResetLabel -and -not [string]::IsNullOrWhiteSpace([string]$ResetLabel)) {
        [string]$ResetLabel
    } else {
        'n/a'
    }
    # U+00B7 by char code: a literal here is mis-decoded (A-circumflex + dot) by Windows PowerShell 5.1.
    return ('{0}  {1} {3} {2}' -f $GroupLabel, $PctLabel, $reset, [char]0x00B7)
}

function Select-BobCursorGroupRemainMinimum {
    param([AllowNull()]$Values)
    $known = @()
    foreach ($v in @($Values)) {
        if ($null -eq $v) { continue }
        try { $known += ,[int]$v } catch { }
    }
    if ($known.Count -eq 0) { return $null }
    return ($known | Measure-Object -Minimum).Minimum
}

function Get-BobCursorGroupPeriodEndForTray {
    param(
        $LocalCursorDoc,
        $SeatCacheEntry,
        [string]$GroupId,
        [switch]$OnSeat
    )
    $gid = [string]$GroupId
    if ($OnSeat -and $LocalCursorDoc) {
        if ($gid -eq 'grok-chat') {
            # FR #448: Sand weekly reset only — never Cursor billingCycleEnd.
            if ($LocalCursorDoc.sand_period_end) { return [string]$LocalCursorDoc.sand_period_end }
            return $null
        }
        elseif ($LocalCursorDoc.period_end) {
            return [string]$LocalCursorDoc.period_end
        }
    }
    if ($SeatCacheEntry -and $SeatCacheEntry.groups) {
        $g = $SeatCacheEntry.groups.$gid
        if ($g -and $g.period_end) { return [string]$g.period_end }
    }
    if ($SeatCacheEntry -and $SeatCacheEntry.period_end -and $gid -ne 'grok-chat') {
        return [string]$SeatCacheEntry.period_end
    }
    return $null
}

function Resolve-BobCursorPcentRowMapping {
    param($Pc, [string]$MachineId)
    if (-not $Pc) { return $null }
    $src = [string]$Pc.source
    if (-not $src) { return $null }
    $pct = ConvertTo-BobTrayIntOrNull $Pc.pct
    if ($null -eq $pct) { return $null }
    $reportMac = [string]$Pc.machine
    if ($reportMac) { $reportMac = Resolve-BobiverseMachineId $reportMac }
    $seatId = $src
    $groupId = $null
    if ($src -eq 'cursor-models' -or $src -eq 'low-cost-models') {
        $groupId = 'low-cost-models'
        $macForSeat = $MachineId
        if ($reportMac) { $macForSeat = $reportMac }
        $seat = Get-BobSeatForMachine -MachineId $macForSeat
        if ($seat) { $seatId = [string]$seat.id }
    }
    elseif ($src -eq 'grok-chat' -or $src -eq 'high-cost-models') {
        $groupId = $src
        $macForSeat = $MachineId
        if ($reportMac) { $macForSeat = $reportMac }
        $seat = Get-BobSeatForMachine -MachineId $macForSeat
        if ($seat) { $seatId = [string]$seat.id }
    }
    elseif ($src -match '^(smart-catalogue|club-madeira|ntsa)$') {
        $seatId = $src
        $groupId = 'low-cost-models'
    }
    if (-not $groupId) { return $null }
    return [pscustomobject]@{ seat_id = $seatId; group_id = $groupId; pct = $pct }
}

function Set-BobCursorControlPoolRow {
    param($Pool, $RemainingPct, [string]$PeriodEnd, $FetchedAt = $null)
    # Null pool is a no-op: an unbound $row here crashed every tray hover with
    # "The property 'remaining_pct' cannot be found on this object" (empty TipForm).
    if ($null -eq $Pool) { return }
    $resetLabel = Format-BobResetLabel -PeriodEnd $PeriodEnd -FetchedAt $FetchedAt
    $pctLabel = Format-BobCursorControlPoolPctLabel $RemainingPct
    $heading = Format-BobCursorControlPoolHeading -GroupLabel ([string]$Pool.group_label) -PctLabel $pctLabel -ResetLabel $resetLabel
    # Digest pools expose `remaining` (not remaining_pct); tray rows expose remaining_pct.
    # Assign tolerantly so either shape (hashtable or PSCustomObject) works.
    $values = [ordered]@{
        remaining_pct = $RemainingPct
        period_end    = $PeriodEnd
        reset_label   = $resetLabel
        pct_label     = $pctLabel
        heading       = $heading
        fetched_at    = $FetchedAt
    }
    if ($Pool -is [System.Collections.IDictionary]) {
        foreach ($k in $values.Keys) { $Pool[$k] = $values[$k] }
        if ($Pool.Contains('remaining')) { $Pool['remaining'] = $RemainingPct }
        return
    }
    foreach ($k in $values.Keys) {
        $Pool | Add-Member -NotePropertyName $k -NotePropertyValue $values[$k] -Force
    }
    if ($null -ne $Pool.PSObject.Properties['remaining']) {
        $Pool | Add-Member -NotePropertyName remaining -NotePropertyValue $RemainingPct -Force
    }
}

function Get-BobDigestPoolPeriodEnd {
    param(
        $DigestPools,
        [string]$GroupId
    )
    $gid = [string]$GroupId
    $aliases = @($gid)
    switch ($gid) {
        'auto' { $aliases = @('auto', 'low-cost-models', 'cursor-models') }
        'low-cost-models' { $aliases = @('low-cost-models', 'auto', 'cursor-models') }
        'high-cost-models' { $aliases = @('high-cost-models', 'other-models') }
        'grok-chat' { $aliases = @('grok-chat', 'grok-weekly', 'sand') }
    }
    foreach ($p in @($DigestPools)) {
        if (-not $p) { continue }
        $pid = [string]$(if ($p.group_id) { $p.group_id } elseif ($p.group) { $p.group } elseif ($p.id) { $p.id } else { '' })
        if (-not $pid) { continue }
        $hit = $false
        foreach ($a in $aliases) {
            if ($pid -eq $a) { $hit = $true; break }
        }
        if (-not $hit) { continue }
        if ($p.period_end) { return [string]$p.period_end }
        if ($p.reset) { return [string]$p.reset }
    }
    return $null
}

function Get-BobCursorPoolsForTray {
    param(
        [string]$MachineId,
        $LocalCursorDoc,
        $PcentRows,
        $DigestPools,
        # FR #445: Write-BobIrcStatus / digest publish must not republish peer pool values.
        [switch]$LocalOnly
    )
    # Cursor Spending groups are per Cursor account on this host — not xAI seat labels
    # (Smart Catalogue / Club Madeira / ntsa are Grok Build seats; see issue #151 UAT).
    $cache = Read-BobCursorPoolsCache
    $catalog = @(Get-BobCursorSpendingGroupCatalog)
    $localSeat = Get-BobSeatForMachine -MachineId $MachineId
    $localSeatId = $null
    $localSeatLabel = $null
    if ($localSeat) {
        $localSeatId = [string]$localSeat.id
        $localSeatLabel = [string]$localSeat.label
        if (-not $localSeatLabel) { $localSeatLabel = $localSeatId }
    }
    $ce = $null
    if ($localSeatId -and $cache.by_seat.ContainsKey($localSeatId)) {
        $ce = $cache.by_seat[$localSeatId]
    }
    $periodEnd = $null
    if ($LocalCursorDoc -and $LocalCursorDoc.period_end) {
        $periodEnd = [string]$LocalCursorDoc.period_end
    }
    if ($ce -and $ce.period_end -and -not $periodEnd) { $periodEnd = [string]$ce.period_end }
    $sandPeriodEnd = $null
    if ($LocalCursorDoc -and $LocalCursorDoc.sand_period_end) {
        $sandPeriodEnd = [string]$LocalCursorDoc.sand_period_end
    }
    $pools = @()
    foreach ($grp in $catalog) {
        $gid = [string]$grp.id
        $glabel = [string]$grp.label
        # FR #445: grok-chat is Sand only — never fall back to Cursor auto / high-cost.
        $remain = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $LocalCursorDoc -GroupId $gid
        if ($null -eq $remain) {
            if ($gid -eq 'grok-chat') {
                # Seat cache may hold sand under groups.'grok-chat' only (not remaining_pct).
                if ($ce -and $ce.groups -and $ce.groups.'grok-chat' -and
                    $null -ne $ce.groups.'grok-chat'.remaining_pct -and
                    [string]$ce.groups.'grok-chat'.remaining_pct -ne '') {
                    try { $remain = [int]$ce.groups.'grok-chat'.remaining_pct } catch { }
                }
            }
            elseif (-not $LocalOnly) {
                $remain = Get-BobCursorGroupRemainFromSeatCache -SeatCacheEntry $ce -GroupId $gid
                if ($null -eq $remain) {
                    # Fleet-shared Cursor auto/high-cost: peer seats may publish; MarchHare TipForm consumes.
                    foreach ($seatEnt in @($cache.by_seat.GetEnumerator())) {
                        $cand = Get-BobCursorGroupRemainFromSeatCache -SeatCacheEntry $seatEnt.Value -GroupId $gid
                        if ($null -eq $cand) { continue }
                        if ($null -eq $remain -or [int]$cand -lt [int]$remain) { $remain = [int]$cand }
                    }
                }
            }
        }
        # 0% is a real value (#179) — only missing/null is n/a.
        $pctLabel = 'n/a'
        if ($null -ne $remain -and [string]$remain -ne '') { $pctLabel = ('{0}%' -f [int]$remain) }
        # Per-group reset: grok chat = Sand nextReset ONLY (FR #448 weekly). Never Cursor billingCycleEnd.
        $pe = $null
        if ($gid -eq 'grok-chat') {
            if ($sandPeriodEnd) { $pe = $sandPeriodEnd }
            elseif ($ce -and $ce.groups -and $ce.groups.'grok-chat' -and $ce.groups.'grok-chat'.period_end) {
                $pe = [string]$ce.groups.'grok-chat'.period_end
            }
        }
        else {
            $pe = $periodEnd
            if (-not $LocalOnly) {
                if ($ce -and $ce.groups) {
                    $ge = $ce.groups.$gid
                    if (-not $ge -and $gid -eq 'auto') { $ge = $ce.groups.'low-cost-models' }
                    if ($ge -and $ge.period_end) { $pe = [string]$ge.period_end }
                }
                if ($null -eq $pe -or $pe -eq '') {
                    foreach ($seatEnt in @($cache.by_seat.GetEnumerator())) {
                        if (-not $seatEnt.Value.groups) { continue }
                        $ge = $seatEnt.Value.groups.$gid
                        if ($ge -and $ge.period_end) { $pe = [string]$ge.period_end; break }
                    }
                }
            }
            elseif ($ce -and $ce.groups) {
                $ge = $ce.groups.$gid
                if (-not $ge -and $gid -eq 'auto') { $ge = $ce.groups.'low-cost-models' }
                if ($ge -and $ge.period_end) { $pe = [string]$ge.period_end }
            }
        }
        # Digest may fill still-null period_end (reset countdown) without clobbering local %.
        if ((-not $pe -or $pe -eq '') -and -not $LocalOnly -and $DigestPools) {
            $pe = Get-BobDigestPoolPeriodEnd -DigestPools $DigestPools -GroupId $gid
        }
        $fetchedAt = $null
        if ($LocalCursorDoc -and $LocalCursorDoc.fetched_at) { $fetchedAt = [string]$LocalCursorDoc.fetched_at }
        $resetLabel = Format-BobResetLabel -PeriodEnd $pe -FetchedAt $fetchedAt
        $heading = Format-BobCursorControlPoolHeading -GroupLabel $glabel -PctLabel $pctLabel -ResetLabel $resetLabel
        $pools += ,[pscustomobject]@{
            seat_id         = $localSeatId
            seat_label      = $localSeatLabel
            group_id        = $gid
            group_label     = $glabel
            remaining_pct   = $remain
            period_end      = $pe
            reset_label     = $resetLabel
            pct_label       = $pctLabel
            overage_label   = $null
            heading         = $heading
            account_name    = $glabel
            fetched_at      = $fetchedAt
        }
    }
    # CAST IRON (Simon 2026-09-27): Cursor pool remaining is a LOCAL Spending check
    # (Get-BobCursorAgentWeeklyRemaining / GetCurrentPeriodUsage). Never use digest to
    # decide whether a pool exists or to overwrite a known local/cache value. Digest
    # pcent may only FILL a still-null bar (hosts with no Cursor login, e.g. MarchHare).
    foreach ($pc in @($PcentRows)) {
        if (-not $pc) { continue }
        $src = [string]$pc.source
        if (-not $src) { continue }
        $pct = ConvertTo-BobTrayIntOrNull $pc.pct
        if ($null -eq $pct) { continue }
        $reportMac = [string]$pc.machine
        if ($reportMac) { $reportMac = Resolve-BobiverseMachineId $reportMac }
        $seatId = $localSeatId
        $groupId = $null
        if ($src -eq 'cursor-models' -or $src -eq 'low-cost-models' -or $src -eq 'auto') {
            $groupId = 'auto'
        }
        elseif ($src -eq 'grok-chat' -or $src -eq 'grok-weekly' -or $src -eq 'sand') {
            $groupId = 'grok-chat'
        }
        elseif ($src -eq 'high-cost-models' -or $src -eq 'other-models') {
            $groupId = 'high-cost-models'
        }
        elseif ($src -match '^(smart-catalogue|club-madeira|ntsa)$') {
            $seatId = $src
            $groupId = 'auto'
            if ($seatId -and $localSeatId -and [string]$seatId -ne [string]$localSeatId) { continue }
        }
        else { continue }
        if (-not $groupId) { continue }
        if ($reportMac) {
            $macSeat = Get-BobSeatForMachine -MachineId $reportMac
            if ($macSeat) { $seatId = [string]$macSeat.id }
        }
        foreach ($pool in $pools) {
            if ([string]$pool.group_id -ne $groupId) { continue }
            # Local/cache already set this bar — digest must not clobber (incl. with n/a path).
            if ($null -ne $pool.remaining_pct -and [string]$pool.remaining_pct -ne '') { break }
            $pool.remaining_pct = $pct
            $pool.pct_label = ('{0}%' -f $pct)
            if ((-not $pool.period_end -or [string]$pool.period_end -eq '') -and $DigestPools) {
                $fillPe = Get-BobDigestPoolPeriodEnd -DigestPools $DigestPools -GroupId $groupId
                if ($fillPe) {
                    $pool.period_end = $fillPe
                    $pool.reset_label = Format-BobResetLabel -PeriodEnd $fillPe -FetchedAt $pool.fetched_at
                }
            }
            $pool.heading = Format-BobCursorControlPoolHeading -GroupLabel ([string]$pool.group_label) -PctLabel $pool.pct_label -ResetLabel $pool.reset_label
            break
        }
        foreach ($seat in @(Get-BobSeatConfig)) {
            if (-not $seat -or -not $seat.id) { continue }
            $sid = [string]$seat.id
            Save-BobCursorPoolGroupForSeat -SeatId $sid -GroupId $groupId -RemainingPct $pct
            if ($groupId -eq 'low-cost-models' -or $groupId -eq 'auto') {
                Save-BobCursorPoolForSeat -SeatId $sid -RemainingPct $pct
            }
        }
    }
    return $pools
}

function ConvertTo-BobTrayJobRow {
    param($Job, [string]$DefaultMachine, [string]$State, [switch]$SkipGit)
    $id = [string]$Job.id
    $sid = $id
    if ($Job.sessionId) { $sid = [string]$Job.sessionId }
    $ctx = $null
    if (-not $SkipGit) {
        $ctx = Get-SessionContextRemaining -Cwd $Job.cwd -SessionId $sid
    }
    $mac = [string]$Job.machine
    if (-not $mac) { $mac = $DefaultMachine }
    $when = $Job.claimedAt
    if (-not $when) { $when = $Job.createdAt }
    $st = $State
    if (-not $st) {
        if ($Job.state) { $st = [string]$Job.state } else { $st = 'running' }
    }
    $fields = Get-BobJobTrayFields -Job $Job -SkipGit:$SkipGit
    $repo = '?'
    if ($fields -and $fields.repo) { $repo = $fields.repo }
    $line = Format-BobTrayJobLine -Job $Job -SkipGit:$SkipGit
    return [pscustomobject]@{
        id                     = $id
        id8                    = $(if ($id.Length -ge 8) { $id.Substring(0, 8) } else { $id })
        machine                = $mac
        repo                   = $repo
        sha                    = $(if ($fields) { $fields.sha } else { $null })
        model                  = $(if ($fields) { $fields.model } else { $null })
        description            = $(if ($fields) { $fields.description } else { $null })
        run_time               = $(if ($fields) { $fields.run_time } else { $null })
        duration               = Get-BobJobAge $when
        state                  = $st
        line                   = $line
        cwd                    = [string]$Job.cwd
        context_remaining_pct  = $(if ($ctx) { [int]$ctx.remaining_pct } else { $null })
    }
}

function Get-BobTrayHover {
    $tier = '?'
    try {
        $path = Join-Path $env:USERPROFILE '.grok\settings_cache.json'
        if (Test-Path $path) {
            $wrap = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
            $payload = $wrap.payload
            if ($payload -is [string]) { $payload = $payload | ConvertFrom-Json }
            $t = [string]$payload.settings.subscription_tier_display
            if ($t -match 'Premium') { $tier = 'P+' }
            elseif ($t -match 'SuperGrok') { $tier = 'SG' }
            elseif ($t) { $tier = $t }
            if ($tier.Length -gt 8) { $tier = $tier.Substring(0, 8) }
        }
    }
    catch { }

    $machineId = $null
    try { $machineId = Get-ThisMachineId } catch { }
    if (-not $machineId) { $machineId = 'this-machine' }
    $title = Get-BobTrayTitle -MachineId $machineId

    $reportDigest = $null
    try { $reportDigest = Read-BobReportDigest } catch { $reportDigest = $null }
    # #42: the digest's ChanServ roster (roster_machine_ids, bobiverse#33) is the ONLY source
    # of Grok-account rows when present - no hardcoded config nicks (e.g. legacy 'ionos').
    # Set before Expand-BobReportDigestView so Resolve-BobiverseMachineId accepts roster ids.
    $script:BobRosterIds = @()
    if ($reportDigest -and $reportDigest.roster_machine_ids) {
        # v0.1.19 (#79): fold legacy aliases (ionos -> win-mpre8vi4u6u) and de-dupe BEFORE any set is built from the roster.
        $script:BobRosterIds = @(Select-BobUniqueCanonicalIds @($reportDigest.roster_machine_ids))
    }
    # #42: digest has no roster (older chair / offline) => ONLY the local machine plus whatever
    # the digest's `machines` keys contain. Never the bobiverse.json nick list.
    if ($script:BobRosterIds.Count -eq 0) {
        $fallbackIds = @()
        if ($machineId -and $machineId -ne 'this-machine') { $fallbackIds += ([string]$machineId).ToLowerInvariant() }
        if ($reportDigest -and $reportDigest.machines) {
            foreach ($mp in @($reportDigest.machines.PSObject.Properties)) {
                if ($mp.Name) { $fallbackIds += ([string]$mp.Name).Trim().ToLowerInvariant() }
            }
        }
        $script:BobRosterIds = @(Select-BobUniqueCanonicalIds @($fallbackIds | Where-Object { $_ }))
    }
    $digestView = Expand-BobReportDigestView -Digest $reportDigest
    $digestTasksByMachine = $digestView.tasksByMachine
    $uptimeByMachine = $digestView.uptimeByMachine
    $digestPcentRows = @($digestView.pcentRows)
    $digestWeeklyRows = @($digestView.weeklyRows)
    $digestWorkersByMachine = @{}
    if ($digestView.workersByMachine) { $digestWorkersByMachine = $digestView.workersByMachine }

    $running = @()
    $queuedJobs = @()
    try { $running = @(Get-BobBuilds -Lane running -ErrorAction SilentlyContinue) } catch { }
    try { $queuedJobs = @(Get-BobBuilds -Lane inbox -ErrorAction SilentlyContinue) } catch { }
    $queued = @($queuedJobs).Count

    $jobs = @()
    $localIds = @{}
    foreach ($b in $running) {
        $row = ConvertTo-BobTrayJobRow -Job $b -DefaultMachine $machineId -State $(if ($b.state) { [string]$b.state } else { 'running' })
        $jobs += ,$row
        if ($row.id) { $localIds[$row.id] = $true }
    }
    foreach ($b in $queuedJobs) {
        $row = ConvertTo-BobTrayJobRow -Job $b -DefaultMachine $machineId -State 'queued'
        $jobs += ,$row
        if ($row.id) { $localIds[$row.id] = $true }
    }
    $fleetSessions = @{}
    foreach ($b in @($running)) {
        if ($b.sessionId) { $fleetSessions[[string]$b.sessionId] = $true }
        if ($b.id) { $fleetSessions[[string]$b.id] = $true }
    }
    foreach ($g in @(Get-BobLiveGrokAgents)) {
        if ($g.id -and ($localIds.ContainsKey([string]$g.id) -or $fleetSessions.ContainsKey([string]$g.id))) { continue }
        if ($g.sessionId -and $fleetSessions.ContainsKey([string]$g.sessionId)) { continue }
        $row = ConvertTo-BobTrayJobRow -Job $g -DefaultMachine $machineId -State 'running'
        if (-not $row.line) { continue }
        $jobs += ,$row
        if ($row.id) { $localIds[$row.id] = $true }
    }

    $reg = $null
    try { $reg = Get-BobFleetRegistry } catch { }
    $staleAfter = 900
    $peekMs = 1500
    $shareRoot = $null
    if ($reg) {
        if ($reg.staleAfterSec) { $staleAfter = [int]$reg.staleAfterSec }
        if ($reg.peekTimeoutMs) { $peekMs = [int]$reg.peekTimeoutMs }
        if ($reg.shareRoot) { $shareRoot = [string]$reg.shareRoot }
    }

    $byMachine = @{}
    $reachBy = @{}
    $seenBy = @{}
    $specBy = @{}
    $seatIds = @()
    # #42: ChanServ roster from the digest, else local + digest machine keys (see above).
    # bobiverse.json nicks are NOT consulted for the Grok accounts rows.
    $seatIds = @(Select-BobUniqueCanonicalIds @($script:BobRosterIds))
    $knownTile = @{}
    if ($machineId) { $knownTile[$machineId] = $true }
    foreach ($sid in $seatIds) { if ($sid) { $knownTile[$sid] = $true } }
    $restrictTiles = $knownTile.Count -gt 1 -or ($seatIds.Count -gt 0)
    if ($reg) {
        foreach ($m in @($reg.machines)) {
            $mid = Get-BobCanonicalMachineId ([string]$m.id)
            if (-not $mid) { continue }
            if ($restrictTiles -and -not $knownTile.ContainsKey($mid)) { continue }
            if (-not $byMachine.ContainsKey($mid)) { $byMachine[$mid] = @() }
            $specBy[$mid] = $m
        }
    }
    foreach ($sid in $seatIds) {
        if (-not $byMachine.ContainsKey($sid)) { $byMachine[$sid] = @() }
    }
    if (-not $byMachine.ContainsKey($machineId)) {
        $byMachine[$machineId] = @()
    }
    $reachBy[$machineId] = 'local'
    $weeklyBy = @{}
    $periodEndBy = @{}
    $weekFetchedBy = @{}
    $week = Get-BobWeeklyRemaining
    $remainPct = $null
    $weekFetched = $null
    # CAST IRON AgentMonitor#150: a local unified.jsonl read (incl. Grok 1.0.41
    # remaining_pct=$null / TipForm n/a) locks this host. Digest weekly=0 or
    # seat-period-end cache must not paint exhaustion over local n/a.
    $localWeeklyLocked = [bool]$week
    if ($week -and (Test-BobTrayRemainingKnown $week.remaining_pct)) {
        $remainPct = [int]$week.remaining_pct
        $weekFetched = [string]$week.fetched_at
        $weeklyBy[$machineId] = $remainPct
        if ($weekFetched) { $weekFetchedBy[$machineId] = $weekFetched }
    }
    if ($week -and $week.period_end) {
        $periodEndBy[$machineId] = [string]$week.period_end
    }
    if ($week) {
        Save-BobSeatPeriodEnd -MachineId $machineId -PeriodEnd $(if ($week.period_end) { [string]$week.period_end } else { $null }) -Weekly $(if ($null -ne $week.remaining_pct -and (Test-BobTrayRemainingKnown $week.remaining_pct)) { [int]$week.remaining_pct } else { $null }) -ClearWeekly:([bool]$week.stale)
    }
    foreach ($pc in @($digestPcentRows)) {
        if (-not $pc) { continue }
        $src = [string]$pc.source
        $mac = [string]$pc.machine
        if ($mac) { $mac = Resolve-BobiverseMachineId $mac }
        $pct = ConvertTo-BobTrayIntOrNull $pc.pct
        if ($null -eq $pct) { continue }
        if ($src -eq 'grok-build' -and $mac) {
            # FR AgentMonitor#150 / CAST IRON: this host's Grok weekly is LOCAL unified.jsonl.
            # Digest may fill peer tiles only; never clobber a known local weekly (incl. n/a).
            if ($mac -eq $machineId -and $localWeeklyLocked) { continue }
            $weeklyBy[$mac] = $pct
        }
    }
    # HTTP digest machine.weekly → Grok tiles (#179). 0% is valid for peers.
    foreach ($wr in @($digestWeeklyRows)) {
        if (-not $wr) { continue }
        $mac = [string]$wr.machine
        if ($mac) { $mac = Resolve-BobiverseMachineId $mac }
        if (-not $mac) { continue }
        $pct = ConvertTo-BobTrayIntOrNull $wr.weekly
        if ($null -eq $pct) { continue }
        # FR AgentMonitor#150: digest must not overwrite this host's local Grok pool (incl. n/a).
        if ($mac -eq $machineId -and $localWeeklyLocked) { continue }
        $weeklyBy[$mac] = $pct
        if ($wr.period_end) {
            if (-not ($mac -eq $machineId -and $periodEndBy.ContainsKey($machineId))) {
                $periodEndBy[$mac] = [string]$wr.period_end
            }
        }
        try {
            Save-BobSeatPeriodEnd -MachineId $mac -PeriodEnd $(if ($wr.period_end) { [string]$wr.period_end } else { $null }) -Weekly $pct
        } catch { }
    }
    $cursorWeek = $null
    $cursorRemain = $null
    try { $cursorWeek = Get-BobCursorAgentWeeklyRemaining } catch { $cursorWeek = $null }
    if ($cursorWeek -and (Test-BobTrayRemainingKnown $cursorWeek.remaining_pct)) {
        $cursorRemain = [int]$cursorWeek.remaining_pct
    }

    $moot = $null
    try { $moot = Get-BobMootRoster } catch { $moot = $null }

    foreach ($j in $jobs) {
        $mid = [string]$j.machine
        if (-not $mid) { $mid = $machineId }
        if ($restrictTiles -and -not $knownTile.ContainsKey($mid)) {
            $mid = $machineId
        }
        if (-not $byMachine.ContainsKey($mid)) {
            $byMachine[$mid] = @()
        }
        $byMachine[$mid] += ,$j
        if ($mid -ne $machineId -and -not $reachBy.ContainsKey($mid)) {
            $reachBy[$mid] = 'ok'
        }
    }

    foreach ($mid in @($byMachine.Keys)) {
        if ($mid -eq $machineId) { continue }
        if (@($byMachine[$mid]).Count -gt 0) { continue }
        $spec = $null
        if ($specBy.ContainsKey($mid)) { $spec = $specBy[$mid] }
        else { $spec = [pscustomobject]@{ id = $mid } }
        $peek = $null
        try {
            $peek = Read-BobPeerPeek -Id $mid -Spec $spec -ShareRoot $shareRoot -TimeoutMs $peekMs
        }
        catch { $peek = $null }
        $inMoot = $false
        try { $inMoot = [bool](Test-BobMachineInMoot -MachineId $mid -Roster $moot) } catch { $inMoot = $false }
        if (-not $peek -or -not $peek.ok) {
            if ($inMoot) { $reachBy[$mid] = 'irc-fallback' }
            else { $reachBy[$mid] = 'not-in-moot' }
            continue
        }
        if ($peek.lastSeen) { $seenBy[$mid] = [string]$peek.lastSeen }
        # Never overwrite this host's local unified.jsonl reading (incl. n/a) via peer peek.
        if ($mid -eq $machineId -and $localWeeklyLocked) {
            # keep period_end from peek only when local lacked one
            if ($peek.period_end -and -not ($periodEndBy.ContainsKey($mid) -and $periodEndBy[$mid])) {
                $periodEndBy[$mid] = [string]$peek.period_end
            }
        }
        elseif ($null -ne $peek.weekly -and (Test-BobTrayRemainingKnown $peek.weekly)) {
            $weeklyBy[$mid] = [int]$peek.weekly
            if ($peek.period_end) { $periodEndBy[$mid] = [string]$peek.period_end }
            try {
                Save-BobSeatPeriodEnd -MachineId $mid -PeriodEnd $(if ($peek.period_end) { [string]$peek.period_end } else { $null }) -Weekly ([int]$peek.weekly)
            } catch { }
        }
        elseif ($peek.period_end) {
            $periodEndBy[$mid] = [string]$peek.period_end
            try {
                Save-BobSeatPeriodEnd -MachineId $mid -PeriodEnd ([string]$peek.period_end) -Weekly $null
            } catch { }
        }
        if ($peek.cursor_label -and [string]$peek.cursor_label -ne 'empty') {
            try { Save-BobCursorAccountCache -Label ([string]$peek.cursor_label) -PeriodEnd $(if ($peek.cursor_period_end) { [string]$peek.cursor_period_end } else { $null }) } catch { }
            try {
                $peekSeat = Get-BobSeatForMachine -MachineId $mid
                if ($peekSeat) {
                    Save-BobCursorPoolForSeat -SeatId ([string]$peekSeat.id) -Label ([string]$peek.cursor_label) -PeriodEnd $(if ($peek.cursor_period_end) { [string]$peek.cursor_period_end } else { $null })
                }
            }
            catch { }
        }
        $peerJobs = @()
        if ($peek.jobs) { foreach ($one in $peek.jobs) { $peerJobs += $one } }
        foreach ($pj in $peerJobs) {
            if ($pj.id -and $localIds.ContainsKey([string]$pj.id)) { continue }
            $st = [string]$pj.state
            if (-not $st) { $st = 'running' }
            $byMachine[$mid] += ,(ConvertTo-BobTrayJobRow -Job $pj -DefaultMachine $mid -State $st -SkipGit)
        }
        $age = Get-BobLastSeenAgeSec -Record ([pscustomobject]@{ lastSeen = $peek.lastSeen })
        $empty = (@($byMachine[$mid]).Count -eq 0)
        $fromIrc = @('irc', 'irc-tray', 'irc-digest') -contains ([string]$peek.source)
        # In-moot / IRC peer beats lastSeen-age 'stale' (good card = everyone in the moot).
        if ($inMoot -or $fromIrc) {
            $reachBy[$mid] = 'irc-fallback'
        }
        elseif ($empty -and ($null -eq $age -or $age -gt $staleAfter)) {
            $reachBy[$mid] = 'stale'
        }
        elseif (-not $empty -and $null -ne $age -and $age -gt $staleAfter) {
            $reachBy[$mid] = 'stale'
        }
        else {
            $reachBy[$mid] = 'ok'
        }
    }

    if ($restrictTiles) {
        foreach ($k in @($byMachine.Keys)) {
            if (-not $knownTile.ContainsKey($k)) { $byMachine.Remove($k) }
        }
    }

    # v0.1.19 (#79): fold any alias-keyed bucket into its canonical machine (jobs kept, once) so the same
    # machine can never get two rows.
    foreach ($k in @($byMachine.Keys)) {
        $ck = Get-BobCanonicalMachineId $k
        if ($ck -and $ck -ne $k) {
            if (-not $byMachine.ContainsKey($ck)) { $byMachine[$ck] = @() }
            $byMachine[$ck] = @($byMachine[$ck]) + @($byMachine[$k])
            $byMachine.Remove($k)
        }
    }
    $order = @()
    if ($byMachine.ContainsKey($machineId)) { $order += $machineId }
    foreach ($k in ($byMachine.Keys | Sort-Object)) {
        if ($k -ne $machineId) { $order += $k }
    }

    # Same xAI seat => one shared remaining % (account-level).
    foreach ($seat in @(Get-BobSeatConfig)) {
        $vals = @()
        foreach ($sm in @($seat.machines)) {
            $smid = [string]$sm
            if ($smid -and $weeklyBy.ContainsKey($smid) -and $null -ne $weeklyBy[$smid]) {
                $vals += ,([int]$weeklyBy[$smid])
            }
        }
        if ($vals.Count -gt 0) {
            $shared = ($vals | Measure-Object -Minimum).Minimum
            foreach ($sm in @($seat.machines)) {
                $smid = [string]$sm
                if (-not $smid) { continue }
                if ($smid -eq $machineId -and $localWeeklyLocked -and -not $weeklyBy.ContainsKey($smid)) { continue }
                $weeklyBy[$smid] = [int]$shared
            }
        }
        $ends = @()
        foreach ($sm in @($seat.machines)) {
            $smid = [string]$sm
            if ($smid -and $periodEndBy.ContainsKey($smid) -and $periodEndBy[$smid]) {
                $ends += ,[string]$periodEndBy[$smid]
            }
        }
        if ($ends.Count -gt 0) {
            $sharedEnd = ($ends | Sort-Object | Select-Object -First 1)
            foreach ($sm in @($seat.machines)) {
                $smid = [string]$sm
                if ($smid) { $periodEndBy[$smid] = $sharedEnd }
            }
        }
    }

    # Durable fallback: seat-period-end.json survives IRC import wipes.
    try {
        $peCache = Read-BobSeatPeriodEndCache
        foreach ($mid2 in @($order)) {
            if ($periodEndBy.ContainsKey($mid2) -and $periodEndBy[$mid2]) { continue }
            if ($peCache.by_machine.ContainsKey($mid2) -and $peCache.by_machine[$mid2]) {
                $periodEndBy[$mid2] = [string]$peCache.by_machine[$mid2]
            }
        }
        foreach ($mid2 in @($order)) {
            if ($mid2 -eq $machineId -and $localWeeklyLocked) { continue }
            if ($weeklyBy.ContainsKey($mid2) -and $null -ne $weeklyBy[$mid2]) { continue }
            if ($peCache.weekly_by_machine.ContainsKey($mid2) -and $null -ne $peCache.weekly_by_machine[$mid2]) {
                $weeklyBy[$mid2] = [int]$peCache.weekly_by_machine[$mid2]
            }
        }
        foreach ($seat in @(Get-BobSeatConfig)) {
            $sid = [string]$seat.id
            $seatEnd = $null
            $seatWeek = $null
            if ($sid -and $peCache.by_seat.ContainsKey($sid) -and $peCache.by_seat[$sid]) {
                $seatEnd = [string]$peCache.by_seat[$sid]
            }
            if ($sid -and $peCache.weekly_by_seat.ContainsKey($sid) -and $null -ne $peCache.weekly_by_seat[$sid]) {
                $seatWeek = [int]$peCache.weekly_by_seat[$sid]
            }
            foreach ($sm in @($seat.machines)) {
                $smid = [string]$sm
                if (-not $smid) { continue }
                if ($periodEndBy.ContainsKey($smid) -and $periodEndBy[$smid]) {
                    if (-not $seatEnd) { $seatEnd = [string]$periodEndBy[$smid] }
                }
                elseif ($seatEnd) { $periodEndBy[$smid] = $seatEnd }
                if ($weeklyBy.ContainsKey($smid) -and $null -ne $weeklyBy[$smid]) {
                    if ($null -eq $seatWeek) { $seatWeek = [int]$weeklyBy[$smid] }
                }
                elseif ($null -ne $seatWeek) {
                    if ($smid -eq $machineId -and $localWeeklyLocked) { continue }
                    $weeklyBy[$smid] = [int]$seatWeek
                }
            }
            if ($seatEnd) {
                foreach ($sm in @($seat.machines)) {
                    $smid = [string]$sm
                    if ($smid -and (-not $periodEndBy.ContainsKey($smid) -or -not $periodEndBy[$smid])) {
                        $periodEndBy[$smid] = $seatEnd
                    }
                }
            }
            if ($null -ne $seatWeek) {
                foreach ($sm in @($seat.machines)) {
                    $smid = [string]$sm
                    if ($smid -eq $machineId -and $localWeeklyLocked) { continue }
                    if ($smid -and (-not $weeklyBy.ContainsKey($smid) -or $null -eq $weeklyBy[$smid])) {
                        $weeklyBy[$smid] = [int]$seatWeek
                    }
                }
            }
        }
        # t785u: this host's own reading is stale (the Grok CLI has not refetched billing since the period rolled):
        # show the same account's figure from a seat-mate that reported for the same period.
        if ($week -and $week.stale -and ($null -eq $weeklyBy[$machineId])) {
            $mateWk = Resolve-BobSeatMateWeekly -MachineId $machineId -LocalWeek $week -Seats @(Get-BobSeatConfig) -WeeklyBy $weeklyBy -PeriodEndBy $periodEndBy
            if ($null -ne $mateWk) { $weeklyBy[$machineId] = $mateWk }
        }
        foreach ($k in @($periodEndBy.Keys)) {
            $wk = $null
            if ($weeklyBy.ContainsKey($k)) { $wk = $weeklyBy[$k] }
            if ($periodEndBy[$k] -or $null -ne $wk) {
                Save-BobSeatPeriodEnd -MachineId $k -PeriodEnd $(if ($periodEndBy[$k]) { [string]$periodEndBy[$k] } else { $null }) -Weekly $wk
            }
        }
    } catch { }

    $tiles = @()
    $jobLines = @()
    foreach ($mid in $order) {
        $rows = @($byMachine[$mid])
        if ($digestTasksByMachine.ContainsKey($mid)) {
            $digestRows = @()
            foreach ($dt in @($digestTasksByMachine[$mid])) {
                if (-not $dt) { continue }
                if (-not (Test-BobTrayDigestCodingTask $dt)) { continue }
                $dr = ConvertTo-BobTrayJobRow -Job $dt -DefaultMachine $mid -State ([string]$dt.state) -SkipGit
                if ($dr.line) { $digestRows += ,$dr }
            }
            if ($digestRows.Count -gt 0) { $rows = $digestRows }
        }
        if ($rows.Count -eq 0 -and $digestWorkersByMachine.ContainsKey($mid)) {
            $wi = $digestWorkersByMachine[$mid]
            $seats = @()
            if ($wi.seats) { $seats = @($wi.seats) }
            elseif ($wi.working_on -or $wi.nick) {
                # Legacy single-slot shape
                $seats = @(
                    [pscustomobject]@{
                        nick  = $(if ($wi.nick) { [string]$wi.nick } else { '' })
                        state = 'busy'
                        job   = $(if ($wi.working_on) { [string]$wi.working_on } else { '' })
                    }
                )
            }
            foreach ($seat in $seats) {
                $rows += ,(New-BobTrayIrcWorkerJobRow `
                        -MachineId $mid `
                        -Description ([string]$seat.job) `
                        -Nick ([string]$seat.nick) `
                        -State ([string]$seat.state))
            }
        }
        # Moot ear fallback only when no seat workers (FR #357) — label "ear online", not START.
        if ($rows.Count -eq 0 -and $moot) {
            foreach ($nk in @($moot.nicks)) {
                $mac = Resolve-BobiverseMachineFromIrcNick $nk
                if ($mac -eq $mid) {
                    $rows += ,(New-BobTrayIrcWorkerJobRow -MachineId $mid -Description 'ear online' -Nick $nk -State 'ear online')
                    break
                }
            }
        }
        if ($rows.Count -gt 1) {
            $rows = @(
                $rows | Sort-Object -Property @{
                    Expression = {
                        switch ([string]$_.state) {
                            'running' { 0 }
                            'queued' { 1 }
                            'START' { 0 }
                            default { 2 }
                        }
                    }
                }
            )
        }
        $reach = 'ok'
        if ($reachBy.ContainsKey($mid)) { $reach = [string]$reachBy[$mid] }
        $wPct = $null
        if ($weeklyBy.ContainsKey($mid)) { $wPct = $weeklyBy[$mid] }
        $seatInfo = Get-BobSeatForMachine -MachineId $mid
        $tileEnd = $null
        if ($periodEndBy.ContainsKey($mid)) { $tileEnd = [string]$periodEndBy[$mid] }
        $tileFetched = $null
        if ($weekFetchedBy.ContainsKey($mid)) { $tileFetched = [string]$weekFetchedBy[$mid] }
        $livePeriod = Resolve-BobTrayLivePeriod -Pct $wPct -PeriodEnd $tileEnd -FetchedAt $tileFetched
        $wPct = $livePeriod.pct
        $tileEnd = $livePeriod.period_end
        $tileReset = $livePeriod.reset_label
        $upSince = $null
        if ($uptimeByMachine.ContainsKey($mid)) { $upSince = [string]$uptimeByMachine[$mid] }
        $tileAvail = $null
        $tileAvailReason = $null
        if ($mid -eq $machineId -and (Get-Command Get-BobGrokAvailability -ErrorAction SilentlyContinue)) {
            try {
                $wObj = $null
                if ($week -and $week.period_end) { $wObj = $week }
                elseif ($null -ne $wPct -or $tileEnd) {
                    $wObj = [pscustomobject]@{ remaining_pct = $wPct; period_end = $tileEnd; format = $(if ($week) { $week.format } else { $null }) }
                }
                $av = Get-BobGrokAvailability -Weekly $wObj
                if ($av) {
                    $tileAvail = [string]$av.state
                    $tileAvailReason = [string]$av.reason
                }
            }
            catch { }
        }
        # #60: this machine's pools + overspend from the digest machines.<id> (what its Bob POSTed).
        $dm = Get-BobTrayDigestMachineSummary -Digest $reportDigest -MachineId $mid
        $tileWorkers = @(Get-BobTrayDigestWorkers -Digest $reportDigest -MachineId $mid)
        $tileWorkerLines = @($tileWorkers | ForEach-Object { Format-BobTrayWorkerLine -Worker $_ } | Where-Object { $_ })
        $tile = New-Object psobject -Property @{
            id                   = $mid
            workers              = $tileWorkers
            worker_lines         = $tileWorkerLines
            grok_pools           = @($dm.grok_pools)
            cursor_pools         = @($dm.cursor_pools)
            overspend_gbp        = $dm.overspend_gbp
            overspend_state      = $dm.overspend_state
            job_count            = $rows.Count
            jobs                 = $rows
            reach                = $reach
            last_seen            = $(if ($seenBy.ContainsKey($mid)) { $seenBy[$mid] } else { $null })
            remaining_pct        = $wPct
            period_end           = $tileEnd
            reset_label          = $tileReset
            availability         = $tileAvail
            availability_reason  = $tileAvailReason
            up_since             = $upSince
            seat_id              = $(if ($seatInfo) { [string]$seatInfo.id } else { $null })
            seat_label           = $(if ($seatInfo) { [string]$seatInfo.label } else { $null })
            seat_email           = $(if ($seatInfo) { [string]$seatInfo.email } else { $null })
        }
        $tiles += ,$tile
        $jlName = $mid
        if ($seatInfo -and $seatInfo.label) { $jlName = ('{0}  -  {1}' -f $mid, $seatInfo.label) }
        $machHeading = ('  {0}' -f $jlName)
        if ($null -ne $wPct) { $machHeading = ('{0} ({1}%)' -f $machHeading, [int]$wPct) }
        if ($tileAvail -and $null -eq $wPct) { $machHeading = ('{0} [{1}]' -f $machHeading, $tileAvail) }
        if ($tileReset) { $machHeading = ('{0} - {1}' -f $machHeading, $tileReset) }
        $jobLines += $machHeading
        $tileFuels = @('cursor-models', 'grok-build', 'copilot', 'grok-bot')
        if ($mid -match '2012') { $tileFuels = @() }
        $tile | Add-Member -NotePropertyName fuels -NotePropertyValue $tileFuels -Force
        if ($tileFuels.Count -gt 0) { $jobLines += ('    fuels: {0}' -f ($tileFuels -join ', ')) }
        # FR #352: TipForm/tooltip — out of tokens, open with key.
        # Grok Build exhaustion only (explicit remaining_pct=0 or availability=exhausted).
        # Never Cursor Sand / pcent.grok-chat (those are Spending bars, not xAI weekly).
        $outOfTokens = $false
        if ($tileAvail -eq 'exhausted') { $outOfTokens = $true }
        elseif ($null -ne $wPct -and [int]$wPct -le 0) { $outOfTokens = $true }
        if ($outOfTokens) {
            $jobLines += '    out of tokens, open with key'
            $tile | Add-Member -NotePropertyName out_of_tokens -NotePropertyValue $true -Force
            $tile | Add-Member -NotePropertyName token_hint -NotePropertyValue 'out of tokens, open with key' -Force
        }
        # v0.1.18: one line per worker process "{nick}: {doing|idle}" (Jeeves-maintained digest list).
        foreach ($wl in $tileWorkerLines) { $jobLines += ('    {0}' -f $wl) }
    }
    $peerPeek = $order.Count -gt 1
    if (-not $peerPeek) {
        $jobLines += 'other hosts not in this store'
    }
    $cursorUsed = $null
    $cursorOver = $null
    if ($cursorWeek) {
        if ($null -ne $cursorWeek.used_pct) { $cursorUsed = $cursorWeek.used_pct }
        if ($null -ne $cursorWeek.overspend_pct) { $cursorOver = $cursorWeek.overspend_pct }
    }
    $acctPctLabel = Format-BobCursorAccountLabel -RemainingPct $cursorRemain -UsedPct $cursorUsed
    if ($acctPctLabel -eq 'empty') {
        $gbp = Get-BobCursorOverageGbp
        if ($null -ne $gbp) { $acctPctLabel = ('-{0}{1:N2}' -f [char]0x00A3, [math]::Abs([double]$gbp)) }
    }
    # Fleet-shared Cursor Sand (Grok Bot) — MarchHare etc. often have no local token.
    if (-not $acctPctLabel -or $acctPctLabel -eq 'empty') {
        try {
            $cc = Read-BobCursorAccountCache
            if ($cc -and $cc.label -and [string]$cc.label -ne 'empty') {
                $acctPctLabel = [string]$cc.label
                if (-not $cursorWeek) { $cursorWeek = [pscustomobject]@{} }
                if ($cc.period_end -and -not $cursorWeek.period_end) {
                    $cursorWeek | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$cc.period_end) -Force
                }
            }
        } catch { }
    }
    if ($acctPctLabel -and $acctPctLabel -ne 'empty') {
        $cend = $null
        if ($cursorWeek -and $cursorWeek.period_end) { $cend = [string]$cursorWeek.period_end }
        Save-BobCursorAccountCache -Label $acctPctLabel -PeriodEnd $cend
    }
    try {
        $localSeat = Get-BobSeatForMachine -MachineId $machineId
        if ($localSeat) {
            Save-BobCursorPoolForSeat -SeatId ([string]$localSeat.id) -RemainingPct $cursorRemain -PeriodEnd $(if ($cursorWeek -and $cursorWeek.period_end) { [string]$cursorWeek.period_end } else { $null }) -Label $acctPctLabel
        }
    }
    catch { }
    $digestPools = @()
    if ($reportDigest -and $reportDigest.cursor_pools) { $digestPools = @($reportDigest.cursor_pools) }
    $cursorPools = @(Get-BobCursorPoolsForTray -MachineId $machineId -LocalCursorDoc $cursorWeek -PcentRows $digestPcentRows -DigestPools $digestPools)
    $cursorGroups = @()
    foreach ($pool in $cursorPools) {
        if (-not $pool) { continue }
        $cursorGroups += ,[pscustomobject]@{
            seat_id        = $pool.seat_id
            seat_label     = $pool.seat_label
            group_id       = $pool.group_id
            group_label    = $pool.group_label
            remaining_pct  = $pool.remaining_pct
            pct_label      = $pool.pct_label
            heading        = $pool.heading
            source         = $(
                if ($pool.group_id -eq 'grok-chat') { 'GetSandUsageStatus.usagePercent' }
                elseif ($pool.group_id -eq 'high-cost-models') { 'GetCurrentPeriodUsage.planUsage.apiPercentUsed' }
                else { 'GetCurrentPeriodUsage.planUsage.autoPercentUsed' }
            )
        }
    }
    $poolLines = @()
    foreach ($pool in $cursorPools) {
        if ($pool.heading) { $poolLines += ('  {0}' -f $pool.heading) }
    }
    $ghPosting = $null
    try { $ghPosting = Get-BobGhPostingReadiness } catch { $ghPosting = $null }
    $ghLine = $null
    if ($ghPosting) {
        if ($ghPosting.issue_posting_ready) { $ghLine = 'GitHub issue post: ready' }
        else { $ghLine = 'GitHub issue post: not ready' }
    }
    $jobsText = (($poolLines + $jobLines) -join "`n")
    if ($ghLine) { $jobsText = $jobsText + "`n" + $ghLine }

    $lines = New-Object System.Collections.Generic.List[string]
    if ($null -eq $remainPct) {
        $lines.Add(('{0}  weekly remaining  n/a' -f $tier))
        $short = '{0} {1} run' -f $tier, @($running).Count
    }
    else {
        $lines.Add(('{0}  weekly remaining  {1}%' -f $tier, $remainPct))
        $short = '{0} {1} run  {2}%' -f $tier, @($running).Count, $remainPct
    }
    foreach ($pl in $poolLines) { $lines.Add($pl) }
    foreach ($jl in $jobLines) { $lines.Add($jl) }
    if (@($running).Count -eq 0) {
        if ($null -eq $remainPct) { $short = '{0} idle' -f $tier }
        else { $short = '{0} idle  {1}%' -f $tier, $remainPct }
    }
    if ($short.Length -gt 63) { $short = $short.Substring(0, 63) }

    return [pscustomobject]@{
        title          = $title
        machine        = $machineId
        scope          = $(if ($peerPeek) { 'fleet-peek' } else { 'local-store' })
        short          = $short
        body           = ($lines -join "`n")
        jobs_text      = $jobsText
        remaining_pct  = $remainPct
        remaining_kind = 'weekly'
        weekly_fetched_at = $weekFetched
        job_count      = @($running).Count
        queued         = $queued
        jobs           = @($jobs)
        machines       = $tiles
        peer_peek      = $peerPeek
        tier           = $tier
        cursor_pools   = @($cursorPools)
        cursor_groups  = @($cursorGroups)
        account_name   = 'auto'
        account_label  = $acctPctLabel
        account_remaining_pct = $cursorRemain
        account_overage_gbp = $(if ($null -ne (Get-BobCursorOverageGbp)) { [double](Get-BobCursorOverageGbp) } else { $null })
        account_used_pct = $cursorUsed
        account_period_end = $(if ($cursorWeek -and $cursorWeek.period_end) { [string]$cursorWeek.period_end } else { $null })
        account_reset_label = $(if ($cursorWeek -and $cursorWeek.period_end) { Format-BobResetLabel -PeriodEnd $cursorWeek.period_end -FetchedAt $cursorWeek.fetched_at } else { $null })
        gh_posting          = $ghPosting
        chair_channels      = $(
            if ($reportDigest -and $reportDigest.chair_channels) {
                @($reportDigest.chair_channels | ForEach-Object { [string]$_ })
            } elseif ($reportDigest -and $reportDigest.machines) {
                @(
                    $reportDigest.machines.PSObject.Properties.Name | ForEach-Object {
                        $m = [string]$_
                        if ($m) { '#' + $m.TrimStart('#') }
                    }
                )
            } else { @() }
        )
    }
}

function Get-BobPointCoord {
    param($Value, [string[]]$Names, $Default = 0)
    if ($null -eq $Value) { return $Default }
    foreach ($n in $Names) {
        $v = $null
        $found = $false
        if ($Value -is [System.Collections.IDictionary]) {
            foreach ($k in @($Value.Keys)) {
                if ([string]$k -ceq $n -or [string]$k -eq $n) {
                    $v = $Value[$k]
                    $found = $true
                    break
                }
            }
        }
        if (-not $found) {
            $p = $Value.PSObject.Properties[$n]
            if ($p) {
                $v = $p.Value
                $found = $true
            }
        }
        if (-not $found) {
            try {
                $v = $Value.$n
                if ($null -ne $v) { $found = $true }
            }
            catch { }
        }
        if ($found -and $null -ne $v -and "$v" -ne '') {
            try { return [int]$v } catch { }
        }
    }
    return $Default
}

function ConvertTo-BobTrayRect {
    param($Value)
    if ($null -eq $Value) { return $null }
    $x = Get-BobPointCoord $Value @('X', 'x', 'Left', 'left') -Default $null
    $y = Get-BobPointCoord $Value @('Y', 'y', 'Top', 'top') -Default $null
    $w = Get-BobPointCoord $Value @('Width', 'width') -Default $null
    $h = Get-BobPointCoord $Value @('Height', 'height') -Default $null
    if ($null -eq $w) {
        $right = Get-BobPointCoord $Value @('Right', 'right') -Default $null
        if ($null -ne $right -and $null -ne $x) { $w = $right - $x }
    }
    if ($null -eq $h) {
        $bottom = Get-BobPointCoord $Value @('Bottom', 'bottom') -Default $null
        if ($null -ne $bottom -and $null -ne $y) { $h = $bottom - $y }
    }
    if ($null -eq $x -or $null -eq $y -or $null -eq $w -or $null -eq $h) { return $null }
    if ($w -le 0 -or $h -le 0) { return $null }
    return [pscustomobject]@{
        X      = [int]$x
        Y      = [int]$y
        Width  = [int]$w
        Height = [int]$h
        Right  = [int]($x + $w)
        Bottom = [int]($y + $h)
    }
}

function Get-BobTrayTipPlacement {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$TipWidth,
        [Parameter(Mandatory = $true)][int]$TipHeight,
        $IconRect,
        $Cursor,
        $WorkArea,
        [bool]$AlreadyVisible = $false,
        [int]$CurrentX = 0,
        [int]$CurrentY = 0,
        [int]$Gap = 12,
        [int]$Margin = 8
    )
    if ($AlreadyVisible) {
        return [pscustomobject]@{
            x      = [int]$CurrentX
            y      = [int]$CurrentY
            source = 'sticky'
            moved  = $false
        }
    }

    $icon = ConvertTo-BobTrayRect $IconRect
    $work = ConvertTo-BobTrayRect $WorkArea
    $cx = Get-BobPointCoord $Cursor @('X', 'x')
    $cy = Get-BobPointCoord $Cursor @('Y', 'y')
    $source = 'cursor'
    $x = $cx - $TipWidth
    $y = $cy - $TipHeight - $Gap

    if ($icon) {
        $source = 'icon'
        $workLeft = 0
        $workTop = 0
        $workRight = 0
        $workBottom = 0
        if ($work) {
            $workLeft = $work.X
            $workTop = $work.Y
            $workRight = $work.Right
            $workBottom = $work.Bottom
        }
        $fromBottom = $false
        $fromTop = $false
        $fromLeft = $false
        $fromRight = $false
        if ($work) {
            $fromBottom = ($icon.Bottom -ge ($workBottom - 2))
            $fromTop = ($icon.Y -le ($workTop + 2))
            $fromLeft = ($icon.Right -le ($workLeft + 2))
            $fromRight = ($icon.X -ge ($workRight - 2))
        }
        if ($fromTop -and -not $fromBottom) {
            $x = $icon.Right - $TipWidth
            $y = $icon.Bottom + $Gap
        }
        elseif ($fromLeft -and -not $fromRight -and -not $fromBottom) {
            $x = $icon.Right + $Gap
            $y = $icon.Bottom - $TipHeight
        }
        elseif ($fromRight -and -not $fromBottom) {
            $x = $icon.X - $TipWidth - $Gap
            $y = $icon.Bottom - $TipHeight
        }
        else {
            $x = $icon.Right - $TipWidth
            $y = $icon.Y - $TipHeight - $Gap
        }
    }

    if ($work) {
        $maxX = $work.Right - $TipWidth - $Margin
        $maxY = $work.Bottom - $TipHeight - $Margin
        $minX = $work.X + $Margin
        $minY = $work.Y + $Margin
        if ($maxX -lt $minX) { $maxX = $minX }
        if ($maxY -lt $minY) { $maxY = $minY }
        if ($x -gt $maxX) { $x = $maxX }
        if ($y -gt $maxY) { $y = $maxY }
        if ($x -lt $minX) { $x = $minX }
        if ($y -lt $minY) { $y = $minY }
    }
    else {
        if ($x -lt $Margin) { $x = $Margin }
        if ($y -lt $Margin) { $y = $Margin }
    }

    return [pscustomobject]@{
        x      = [int]$x
        y      = [int]$y
        source = $source
        moved  = $true
    }
}

