function Get-BobiverseConfigPath {
    $envp = [string]$env:BOB_IRC_CONFIG
    if ($envp -and $envp.Trim() -and (Test-Path $envp.Trim())) { return $envp.Trim() }
    Join-Path (Get-ModuleRoot) 'config\bobiverse.json'
}

function Get-BobiverseConfig {
    $p = Get-BobiverseConfigPath
    if (-not (Test-Path $p)) { return $null }
    return (Read-JsonFile $p)
}

function Get-BobiverseMachineIds {
    # #42: NO hardcoded config nicks. Machine ids = the digest's ChanServ roster
    # ($script:BobRosterIds, set by Get-BobTrayHover) plus THIS machine.
    $ids = @()
    if ($script:BobRosterIds) { foreach ($r in @($script:BobRosterIds)) { if ($r) { $ids += ([string]$r).ToLowerInvariant() } } }
    try {
        $self = [string](Get-ThisMachineId)
        if ($self) { $ids += $self.ToLowerInvariant() }
    } catch { }
    return @($ids | Select-Object -Unique)
}

function Resolve-BobiverseMachineId {
    param([string]$Raw)
    if (-not $Raw) { return $null }
    $id = [string]$Raw.Trim()
    if (-not $id) { return $null }
    $cfg = Get-BobiverseConfig
    # #42: legacy handle -> machine name (e.g. ionos -> win-mpre8vi4u6u). Alias only, never a roster.
    if ($cfg -and $cfg.legacyAliases) {
        $al = $cfg.legacyAliases.PSObject.Properties[$id.ToLowerInvariant()]
        if ($al -and $al.Value) { $id = [string]$al.Value }
    }
    if (-not $cfg -or -not $cfg.nicks) { return $id.ToLowerInvariant() }
    $props = @($cfg.nicks.PSObject.Properties)
    # #42: no config nick list => any machine id is accepted (lowercase machine name).
    if ($props.Count -eq 0) { return $id.ToLowerInvariant() }
    foreach ($p in $props) {
        if ([string]$p.Name -eq $id) { return [string]$p.Name }
    }
    foreach ($p in $props) {
        $nk = [string]$p.Value
        if ($nk -and $nk.ToLowerInvariant() -eq $id.ToLowerInvariant()) {
            return [string]$p.Name
        }
    }
    # #42: machine ids from the digest's ChanServ roster resolve even when absent from config nicks.
    if ($script:BobRosterIds -and (@($script:BobRosterIds) -contains $id.ToLowerInvariant())) {
        return $id.ToLowerInvariant()
    }
    return $null
}

function Get-BobCanonicalMachineId {
    # v0.1.19 (#79): the ONE canonical, lower-case machine id used as a key for rosters, tiles, caches and rows.
    # legacyAliases (ionos -> win-mpre8vi4u6u) are folded in; an id the config does not know stays itself
    # (lower-cased) rather than vanishing, so a roster machine is never lost, only de-duplicated.
    param([string]$Raw)
    if (-not $Raw) { return $null }
    $id = ([regex]::Replace([string]$Raw, '[\uFEFF\u200B\u00A0]', '')).Trim().TrimStart('#').ToLowerInvariant()
    if (-not $id) { return $null }
    $r = $null
    try { $r = Resolve-BobiverseMachineId $id } catch { $r = $null }
    if ($r) { return ([string]$r).Trim().ToLowerInvariant() }
    try {
        $cfg = Get-BobiverseConfig
        if ($cfg -and $cfg.legacyAliases) {
            $al = $cfg.legacyAliases.PSObject.Properties[$id]
            if ($al -and $al.Value) { return ([string]$al.Value).Trim().ToLowerInvariant() }
        }
    } catch { }
    return $id
}

function Select-BobUniqueCanonicalIds {
    # Canonicalise + de-duplicate (order preserved).
    param($Ids)
    $seen = @{}
    $out = @()
    foreach ($x in @($Ids)) {
        $c = Get-BobCanonicalMachineId ([string]$x)
        if ($c -and -not $seen.ContainsKey($c)) { $seen[$c] = $true; $out += $c }
    }
    return @($out)
}

function Get-BobIrcShopChannel {
    param([Parameter(Mandatory)][string]$MachineId)
    $mid = Resolve-BobiverseMachineId $MachineId
    if (-not $mid) {
        $t = [string]$MachineId.Trim().ToLowerInvariant()
        if ($t -eq 'dev1') { $mid = 'ce-priority-dev1' }
        else { $mid = [string]$MachineId.Trim() }
    }
    if ($mid -eq 'dev1') { $mid = 'ce-priority-dev1' }
    return '#' + $mid
}

function Get-BobIrcBuilderChannels {
    param([Parameter(Mandatory)][string]$MachineId)
    $cfg = Get-BobiverseConfig
    $fleet = '#bobiverse'
    if ($cfg -and $cfg.channel) {
        $c = [string]$cfg.channel
        if ($c) { $fleet = $c }
    }
    $shop = Get-BobIrcShopChannel -MachineId $MachineId
    return ($fleet + ',' + $shop)
}

function Get-BobWorkerIrcNick {
    param(
        [Parameter(Mandatory)][string]$MachineId,
        [Parameter(Mandatory)][int]$WorkerPid
    )
    $mid = Resolve-BobiverseMachineId $MachineId
    if (-not $mid) { throw "bad machine id: $MachineId" }
    $shortByMid = @{
        flamingo           = 'fl'
        marchhare          = 'mh'
        'win-mpre8vi4u6u'  = 'io'
        'ce-priority-dev1' = 'd1'
    }
    $short = $shortByMid[$mid]
    if (-not $short) { throw "bad machine id: $MachineId" }
    if ($WorkerPid -le 0) { throw 'WorkerPid must be positive' }
    return "w-$short-$WorkerPid"
}

function Resolve-BobiverseMachineFromIrcNick {
    param([string]$Nick)
    if (-not $Nick) { return $null }
    $n = [string]$Nick.Trim()
    if (-not $n) { return $null }
    $byId = Resolve-BobiverseMachineId $n
    if ($byId) { return $byId }
    $cfg = Get-BobiverseConfig
    if ($cfg -and $cfg.nicks) {
        foreach ($p in @($cfg.nicks.PSObject.Properties)) {
            $nk = [string]$p.Value
            if ($nk -and ($nk -eq $n -or $nk.ToLowerInvariant() -eq $n.ToLowerInvariant())) {
                return [string]$p.Name
            }
        }
    }
    $nl = $n.ToLowerInvariant()
    if ($nl -match '^bob-(.+)$') {
        $tail = [string]$Matches[1]
        $c = Resolve-BobiverseMachineId $tail
        if ($c) { return $c }
        foreach ($mid in @(Get-BobiverseMachineIds)) {
            if ($tail -eq $mid) { return $mid }
        }
    }
    foreach ($mid in @(Get-BobiverseMachineIds)) {
        $ml = $mid.ToLowerInvariant()
        if ($nl -eq $ml) { return $mid }
        if ($nl -match ('^' + [regex]::Escape($ml) + '-\d+$')) { return $mid }
    }
    return $null
}

function Get-BobIrcHome {
    if ($env:BOB_IRC_HOME -and $env:BOB_IRC_HOME.Trim()) {
        return [IO.Path]::GetFullPath($env:BOB_IRC_HOME.Trim())
    }
    if ($env:BOB_HOME -and $env:BOB_HOME.Trim()) {
        return [IO.Path]::GetFullPath($env:BOB_HOME.Trim())
    }
    return [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.bobiverse'))
}

function Get-BobMootRoster {
    $cfg = Get-BobiverseConfig
    $nicks = @()
    $nickToId = @{}
    $idToNick = @{}
    if ($cfg -and $cfg.nicks) {
        foreach ($p in @($cfg.nicks.PSObject.Properties)) {
            $id = [string]$p.Name
            $nk = [string]$p.Value
            if (-not $id -or -not $nk) { continue }
            $idToNick[$id] = $nk
            $nickToId[$nk.ToLowerInvariant()] = $id
        }
    }
    $mid = $null
    if ($cfg) { $mid = [string]$cfg.mootId }
    $home = Get-BobIrcHome
    $roster = @()
    if ($mid -and $home) {
        $stPath = Join-Path $home (Join-Path 'moot' ($mid + '.json'))
        $st = Read-JsonFile $stPath
        if ($st -and $st.roster) {
            foreach ($n in @($st.roster)) {
                $s = [string]$n
                if ($s) { $roster += $s.ToLowerInvariant() }
            }
        }
        if ($st -and $st.chair) {
            $c = [string]$st.chair
            if ($c) {
                $cl = $c.ToLowerInvariant()
                if ($roster -notcontains $cl) { $roster += $cl }
            }
        }
    }
    return [pscustomobject]@{
        nicks     = $roster
        nickToId  = $nickToId
        idToNick  = $idToNick
        mootId    = $mid
    }
}

function Test-BobMachineInMoot {
    param([string]$MachineId, $Roster)
    if (-not $MachineId) { return $false }
    if (-not $Roster) { return $false }
    $self = Get-ThisMachineId
    if ($self -and $MachineId -eq $self -and @($Roster.nicks).Count -gt 0) { return $true }
    if ($Roster.idToNick.ContainsKey($MachineId)) {
        $nk = [string]$Roster.idToNick[$MachineId]
        if ($nk -and ($Roster.nicks -contains $nk.ToLowerInvariant())) { return $true }
        # Registered bobiverse seat (nicks key). Prefer irc-fallback over
        # not-in-moot even when the live MODE2 roster file is empty/stale.
        return $true
    }
    return $false
}

function Get-BobIrcNick {
    param($Config, [string]$MachineId)
    if ($env:BOB_IRC_NICK -and $env:BOB_IRC_NICK.Trim()) { return $env:BOB_IRC_NICK.Trim() }
    if ($Config -and $Config.nicks) {
        $n = $Config.nicks.$MachineId
        if ($n) { return [string]$n }
    }
    if ($MachineId) { return ('bob-' + $MachineId) }
    return $null
}



function Get-BobCursorAccountCachePath {
    try { return (Join-Path (Get-BridgeRoot) 'cursor-account.json') } catch { return $null }
}

function Save-BobCursorAccountCache {
    param([string]$Label, [string]$PeriodEnd)
    if (-not $Label -or $Label -eq 'empty') { return }
    $p = Get-BobCursorAccountCachePath
    if (-not $p) { return }
    $doc = [pscustomobject]@{
        label      = [string]$Label
        period_end = $(if ($PeriodEnd) { [string]$PeriodEnd } else { $null })
        updated_at = [DateTime]::UtcNow.ToString('o')
    }
    try { Write-JsonFile $p $doc } catch { }
}

function Read-BobCursorAccountCache {
    $p = Get-BobCursorAccountCachePath
    if (-not $p -or -not (Test-Path $p)) { return $null }
    try { return Read-JsonFile $p } catch { return $null }
}

function Get-BobCursorPoolsCachePath {
    try { return (Join-Path (Get-BridgeRoot) 'cursor-pools.json') } catch { return $null }
}

function Read-BobCursorPoolsCache {
    $p = Get-BobCursorPoolsCachePath
    if (-not $p -or -not (Test-Path $p)) {
        return [pscustomobject]@{ by_seat = @{} }
    }
    try {
        $j = Read-JsonFile $p
        $by = @{}
        if ($j.by_seat) {
            foreach ($prop in $j.by_seat.PSObject.Properties) {
                $by[$prop.Name] = $prop.Value
            }
        }
        return [pscustomobject]@{ by_seat = $by }
    }
    catch {
        return [pscustomobject]@{ by_seat = @{} }
    }
}

function Parse-BobCursorPoolLabel {
    param([string]$Label)
    if (-not $Label -or $Label -eq 'empty') { return $null }
    $l = [string]$Label.Trim()
    if ($l -match '^(\d+)%$') {
        return [pscustomobject]@{
            remaining_pct = [int]$Matches[1]
            label         = $l
            overage       = $null
        }
    }
    if (($l -match '^-') -or ($l.IndexOf([char]0x00A3) -ge 0)) {
        return [pscustomobject]@{
            remaining_pct = $null
            label         = $l
            overage       = $l
        }
    }
    return [pscustomobject]@{
        remaining_pct = $null
        label         = $l
        overage       = $null
    }
}

function Save-BobCursorPoolGroupForSeat {
    param(
        [Parameter(Mandatory)][string]$SeatId,
        [Parameter(Mandatory)][string]$GroupId,
        $RemainingPct,
        [string]$PeriodEnd
    )
    $sid = [string]$SeatId
    $gid = [string]$GroupId
    if (-not $sid -or -not $gid) { return }
    $p = Get-BobCursorPoolsCachePath
    if (-not $p) { return }
    $cache = Read-BobCursorPoolsCache
    $entry = $null
    if ($cache.by_seat.ContainsKey($sid)) { $entry = $cache.by_seat[$sid] }
    if (-not $entry) { $entry = [pscustomobject]@{} }
    $groups = @{}
    if ($entry.groups) {
        foreach ($gp in @($entry.groups.PSObject.Properties)) {
            $groups[[string]$gp.Name] = $gp.Value
        }
    }
    $grow = [pscustomobject]@{}
    if ($groups.ContainsKey($gid)) { $grow = $groups[$gid] }
    if ($null -ne $RemainingPct -and [string]$RemainingPct -ne '') {
        $grow | Add-Member -NotePropertyName remaining_pct -NotePropertyValue ([int]$RemainingPct) -Force
    }
    if ($PeriodEnd) {
        $grow | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$PeriodEnd) -Force
    }
    $grow | Add-Member -NotePropertyName updated_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $groups[$gid] = $grow
    $entry | Add-Member -NotePropertyName groups -NotePropertyValue ([pscustomobject]$groups) -Force
    $cache.by_seat[$sid] = $entry
    $out = [pscustomobject]@{ by_seat = $cache.by_seat }
    try { Write-JsonFile $p $out } catch { }
}

function Save-BobCursorPoolForSeat {
    param(
        [Parameter(Mandatory)][string]$SeatId,
        $RemainingPct,
        [string]$PeriodEnd,
        [string]$Label
    )
    $sid = [string]$SeatId
    if (-not $sid) { return }
    $p = Get-BobCursorPoolsCachePath
    if (-not $p) { return }
    $cache = Read-BobCursorPoolsCache
    $entry = $null
    if ($cache.by_seat.ContainsKey($sid)) { $entry = $cache.by_seat[$sid] }
    if (-not $entry) { $entry = [pscustomobject]@{} }
    if ($null -ne $RemainingPct -and [string]$RemainingPct -ne '') {
        $entry | Add-Member -NotePropertyName remaining_pct -NotePropertyValue ([int]$RemainingPct) -Force
    }
    if ($Label) {
        $parsed = Parse-BobCursorPoolLabel $Label
        if ($parsed) {
            if ($null -ne $parsed.remaining_pct) {
                $entry | Add-Member -NotePropertyName remaining_pct -NotePropertyValue ([int]$parsed.remaining_pct) -Force
            }
            $entry | Add-Member -NotePropertyName label -NotePropertyValue ([string]$parsed.label) -Force
            if ($parsed.overage) {
                $entry | Add-Member -NotePropertyName overage_label -NotePropertyValue ([string]$parsed.overage) -Force
            }
        }
    }
    if ($PeriodEnd) {
        $entry | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$PeriodEnd) -Force
    }
    $entry | Add-Member -NotePropertyName updated_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $cache.by_seat[$sid] = $entry
    $out = [pscustomobject]@{ by_seat = $cache.by_seat }
    try { Write-JsonFile $p $out } catch { }
}

function Get-BobDigestUrl {
    # FR #354: public GET digest is the same document as reportUrl (IIS has no /digest).
    # Never default to bob.ntsa.uk (does not resolve).
    foreach ($cand in @($env:BOB_DIGEST_URL)) {
        if ($cand -and [string]$cand.Trim()) { return [string]$cand.Trim() }
    }
    try {
        $cfg = Get-BobiverseConfig
        if ($cfg -and $cfg.digestUrl -and [string]$cfg.digestUrl.Trim()) {
            return [string]$cfg.digestUrl.Trim()
        }
        if ($cfg -and $cfg.reportUrl -and [string]$cfg.reportUrl.Trim()) {
            return [string]$cfg.reportUrl.Trim()
        }
    }
    catch { }
    return 'https://irc.ntsa.uk/bob/v1/report'
}

function Read-BobReportDigestHttp {
    <#
      Public GET digest (#174 / agentic_irc#179). Cache 60s so tray can poll
      every minute without hammering the callback host.
    #>
    $now = [datetime]::UtcNow
    if ($script:BobDigestHttpCache -and $script:BobDigestHttpCacheAt) {
        $age = ($now - [datetime]$script:BobDigestHttpCacheAt).TotalSeconds
        if ($age -ge 0 -and $age -lt 60 -and $script:BobDigestHttpCache) {
            return $script:BobDigestHttpCache
        }
    }
    $url = Get-BobDigestUrl
    try {
        $resp = Invoke-WebRequest -Uri $url -Method GET -UseBasicParsing -TimeoutSec 15 -Headers @{ Accept = 'application/json' }
        if (-not $resp -or [int]$resp.StatusCode -lt 200 -or [int]$resp.StatusCode -ge 300) { return $null }
        # v0.1.18: decode the body as UTF-8 explicitly. Windows PowerShell 5.1 decodes .Content as
        # ISO-8859-1 when the response lacks a charset, which turned U+00B7 into "A-circumflex + dot".
        $j = ConvertFrom-BobUtf8Json -Response $resp
        if (-not $j) { return $null }
        $script:BobDigestHttpCache = $j
        $script:BobDigestHttpCacheAt = $now
        return $j
    }
    catch {
        return $null
    }
}

function ConvertFrom-BobUtf8Json {
    # Parse a web response as UTF-8 JSON regardless of the charset header (bytes, not .Content).
    param($Response)
    if (-not $Response) { return $null }
    $text = $null
    try {
        $ms = $Response.RawContentStream
        if ($ms -and $ms.Length -gt 0) {
            $ms.Position = 0
            $buf = New-Object byte[] ([int]$ms.Length)
            [void]$ms.Read($buf, 0, $buf.Length)
            $text = [System.Text.Encoding]::UTF8.GetString($buf)
        }
    }
    catch { $text = $null }
    if ([string]::IsNullOrEmpty($text)) {
        $text = [string]$Response.Content
        # Repair UTF-8 that was decoded as Latin-1 (every non-ASCII byte became 2+ chars).
        if ($text -match '[\u00C2-\u00F4][\u0080-\u00BF]') {
            try { $text = [System.Text.Encoding]::UTF8.GetString([System.Text.Encoding]::GetEncoding(28591).GetBytes($text)) } catch { }
        }
    }
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) { $text = $text.Substring(1) }
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    return ($text | ConvertFrom-Json)
}

function Read-BobReportDigest {
    # Prefer live HTTP digest (agentic_irc #174/#179); fall back to local peer file.
    $http = $null
    try { $http = Read-BobReportDigestHttp } catch { $http = $null }
    if ($http) { return $http }
    $home = $null
    try { $home = Get-BobIrcHome } catch { }
    if (-not $home) { return $null }
    foreach ($name in @('_report-digest.json', 'digest.json')) {
        $p = Join-Path $home (Join-Path 'bob-peers' $name)
        if (-not (Test-Path $p)) { continue }
        try {
            $j = Read-JsonFile $p
            if ($j) { return $j }
        }
        catch { }
    }
    return $null
}

function Get-BobSeatPeriodEndCachePath {
    try { return (Join-Path (Get-BridgeRoot) 'seat-period-end.json') } catch { return $null }
}

function Read-BobSeatPeriodEndCache {
    $p = Get-BobSeatPeriodEndCachePath
    if (-not $p -or -not (Test-Path $p)) {
        return [pscustomobject]@{ by_machine = @{}; by_seat = @{}; weekly_by_machine = @{}; weekly_by_seat = @{} }
    }
    try {
        $j = Read-JsonFile $p
        if (-not $j) { return [pscustomobject]@{ by_machine = @{}; by_seat = @{}; weekly_by_machine = @{}; weekly_by_seat = @{} } }
        $bm = @{}; $bs = @{}; $wm = @{}; $ws = @{}
        if ($j.by_machine) {
            foreach ($p2 in $j.by_machine.PSObject.Properties) {
                # Back-compat: string value = period_end only
                if ($p2.Value -is [string] -or $p2.Value -is [datetime]) {
                    $bm[$p2.Name] = [string]$p2.Value
                }
                elseif ($p2.Value) {
                    if ($p2.Value.period_end) { $bm[$p2.Name] = [string]$p2.Value.period_end }
                    if ($null -ne $p2.Value.weekly) { $wm[$p2.Name] = [int]$p2.Value.weekly }
                }
            }
        }
        if ($j.by_seat) {
            foreach ($p2 in $j.by_seat.PSObject.Properties) {
                if ($p2.Value -is [string] -or $p2.Value -is [datetime]) {
                    $bs[$p2.Name] = [string]$p2.Value
                }
                elseif ($p2.Value) {
                    if ($p2.Value.period_end) { $bs[$p2.Name] = [string]$p2.Value.period_end }
                    if ($null -ne $p2.Value.weekly) { $ws[$p2.Name] = [int]$p2.Value.weekly }
                }
            }
        }
        if ($j.weekly_by_machine) {
            foreach ($p2 in $j.weekly_by_machine.PSObject.Properties) {
                try { $wm[$p2.Name] = [int]$p2.Value } catch { }
            }
        }
        if ($j.weekly_by_seat) {
            foreach ($p2 in $j.weekly_by_seat.PSObject.Properties) {
                try { $ws[$p2.Name] = [int]$p2.Value } catch { }
            }
        }
        return [pscustomobject]@{ by_machine = $bm; by_seat = $bs; weekly_by_machine = $wm; weekly_by_seat = $ws }
    }
    catch {
        return [pscustomobject]@{ by_machine = @{}; by_seat = @{}; weekly_by_machine = @{}; weekly_by_seat = @{} }
    }
}

function Save-BobSeatPeriodEnd {
    param(
        [string]$MachineId,
        [string]$PeriodEnd,
        [string]$SeatId,
        $Weekly,
        [switch]$ClearWeekly
    )
    $p = Get-BobSeatPeriodEndCachePath
    if (-not $p) { return }
    if ($MachineId) { $c = Get-BobCanonicalMachineId $MachineId; if ($c) { $MachineId = $c } }   # #79: never write alias-keyed entries
    $cache = Read-BobSeatPeriodEndCache
    if ($MachineId -and $PeriodEnd) { $cache.by_machine[$MachineId] = [string]$PeriodEnd }
    if ($MachineId -and $null -ne $Weekly -and [string]$Weekly -ne '') {
        try { $cache.weekly_by_machine[$MachineId] = [int]$Weekly } catch { }
    }
    if (-not $SeatId -and $MachineId) {
        try {
            $s = Get-BobSeatForMachine -MachineId $MachineId
            if ($s) { $SeatId = [string]$s.id }
        } catch { }
    }
    if ($SeatId -and $PeriodEnd) { $cache.by_seat[$SeatId] = [string]$PeriodEnd }
    # t785u: this host's own reading is stale/unmeasured: drop the % cached from the PREVIOUS period (machine and seat).
    if ($ClearWeekly) {
        if ($MachineId -and $cache.weekly_by_machine.ContainsKey($MachineId)) { $cache.weekly_by_machine.Remove($MachineId) }
        if ($SeatId -and $cache.weekly_by_seat.ContainsKey($SeatId)) { $cache.weekly_by_seat.Remove($SeatId) }
    }
    if ($SeatId -and $null -ne $Weekly -and [string]$Weekly -ne '') {
        try { $cache.weekly_by_seat[$SeatId] = [int]$Weekly } catch { }
    }
    if (-not $PeriodEnd -and $null -eq $Weekly -and -not $ClearWeekly) { return }
    $doc = [pscustomobject]@{
        by_machine         = [pscustomobject]$cache.by_machine
        by_seat            = [pscustomobject]$cache.by_seat
        weekly_by_machine  = [pscustomobject]$cache.weekly_by_machine
        weekly_by_seat     = [pscustomobject]$cache.weekly_by_seat
        updated_at         = [DateTime]::UtcNow.ToString('o')
    }
    try { Write-JsonFile $p $doc } catch { }
}


function Merge-BobIrcPeerRemaining {
    param($Prev, $Incoming)
    if (-not $Incoming) { return $Incoming }
    $keys = @('remaining_pct', 'account_remaining_pct', 'cursor_remaining_pct')
    $rem = $null
    foreach ($k in $keys) {
        $names = @($Incoming.PSObject.Properties.Name)
        if ($names -contains $k -and $null -ne $Incoming.$k -and [string]$Incoming.$k -ne '') {
            try { $rem = [int]$Incoming.$k; break } catch { }
        }
    }
    if ($null -eq $rem -and $Prev) {
        foreach ($k in $keys) {
            $pnames = @($Prev.PSObject.Properties.Name)
            if ($pnames -contains $k -and $null -ne $Prev.$k -and [string]$Prev.$k -ne '') {
                try { $rem = [int]$Prev.$k; break } catch { }
            }
        }
    }
    if ($null -eq $rem) { return $Incoming }
    foreach ($k in $keys) {
        $Incoming | Add-Member -NotePropertyName $k -NotePropertyValue $rem -Force
    }
    return $Incoming
}

function ConvertTo-BobIrcPoint {
    param($Doc)
    $mid = [string]$Doc.id
    $w = '-'
    if ($null -ne $Doc.weekly -and [string]$Doc.weekly -ne '') { $w = [string][int]$Doc.weekly }
    $jobParts = @()
    foreach ($j in @($Doc.jobs)) {
        $repo = ([string]$j.repo).Replace(' ', '')
        $st = ([string]$j.state).Replace(' ', '')
        if (-not $repo -or $repo -eq '?' -or (Test-BobTrayLooksLikeSha $repo)) { continue }
        if ($repo -and $st) { $jobParts += ($repo + ':' + $st) }
    }
    $jobs = '-'
    if ($jobParts.Count -gt 0) { $jobs = ($jobParts -join ',') }
    $seen = [string]$Doc.lastSeen
    if (-not $seen) { $seen = '-' }
    $run = 0
    $q = 0
    if ($Doc.running) { $run = [int]$Doc.running }
    if ($Doc.queued) { $q = [int]$Doc.queued }
    $reset = '-'
    if ($Doc.period_end) {
        try {
            $rd = [datetime]::Parse([string]$Doc.period_end, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
            $reset = $rd.ToUniversalTime().ToString('yyyy-MM-dd')
        } catch { $reset = '-' }
    }
    $cur = '-'
    if ($Doc.cursor_label -and [string]$Doc.cursor_label -ne '' -and [string]$Doc.cursor_label -ne 'empty') {
        $cur = ([string]$Doc.cursor_label).Replace(' ', '')
    }
    $crst = '-'
    if ($Doc.cursor_period_end) {
        try {
            $cd = [datetime]::Parse([string]$Doc.cursor_period_end, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
            $crst = $cd.ToUniversalTime().ToString('yyyy-MM-dd')
        } catch { $crst = '-' }
    }
    $remPart = ''
    foreach ($rk in @('remaining_pct', 'account_remaining_pct', 'cursor_remaining_pct')) {
        $rnames = @($Doc.PSObject.Properties.Name)
        if ($rnames -contains $rk -and $null -ne $Doc.$rk -and [string]$Doc.$rk -ne '') {
            try {
                $remPart = (' remaining={0}' -f [int]$Doc.$rk)
                break
            } catch { }
        }
    }
    $line = "BOB v1 id=$mid weekly=$w reset=$reset cur=$cur crst=$crst running=$run queued=$q lastSeen=$seen jobs=$jobs$remPart"
    if ($line.Length -gt 350) { $line = $line.Substring(0, 349) + '-' }
    return $line
}

function ConvertFrom-BobIrcPoint {
    param([string]$Text)
    if (-not $Text -or $Text -notmatch '^BOB v1 ') { return $null }
    $body = $Text.Substring(7).Trim()
    $kv = @{}
    foreach ($tok in $body.Split(' ')) {
        if ($tok -notmatch '=') { return $null }
        $k, $v = $tok.Split('=', 2)
        $kv[$k] = $v
    }
    $mid = [string]$kv['id']
    if ($mid -notmatch '^[a-z0-9][a-z0-9-]{0,62}$') { return $null }
    $jobs = @()
    $jr = [string]$kv['jobs']
    if ($jr -and $jr -ne '-') {
        foreach ($part in $jr.Split(',')) {
            if ($part -notmatch ':') { continue }
            $repo, $st = $part.Split(':', 2)
            if ((Test-BobIrcRepoOk $repo) -and $st) {
                $jobs += ,[pscustomobject]@{ repo = $repo; state = $st; machine = $mid; id = ($mid + '-' + $jobs.Count) }
            }
        }
    }
    $weekly = $null
    if ($kv.ContainsKey('weekly') -and [string]$kv['weekly'] -ne '-') {
        try { $weekly = [int]$kv['weekly'] } catch { $weekly = $null }
    }
    $run = 0
    $q = 0
    try { $run = [int]$kv['running'] } catch { }
    try { $q = [int]$kv['queued'] } catch { }
    $periodEnd = $null
    if ($kv.ContainsKey('reset') -and [string]$kv['reset'] -ne '-') {
        $periodEnd = [string]$kv['reset']
    }
    $cursorLabel = $null
    if ($kv.ContainsKey('cur') -and [string]$kv['cur'] -ne '-') {
        $cursorLabel = [string]$kv['cur']
    }
    $cursorPeriodEnd = $null
    if ($kv.ContainsKey('crst') -and [string]$kv['crst'] -ne '-') {
        $cursorPeriodEnd = [string]$kv['crst']
    }
    $remainingPct = $null
    foreach ($rk in @('remaining', 'remaining_pct', 'crem')) {
        if ($kv.ContainsKey($rk) -and [string]$kv[$rk] -ne '-' -and [string]$kv[$rk] -ne '') {
            try { $remainingPct = [int]$kv[$rk]; break } catch { $remainingPct = $null }
        }
    }
    $out = [pscustomobject]@{
        ok                = $true
        id                = $mid
        weekly            = $weekly
        period_end        = $periodEnd
        cursor_label      = $cursorLabel
        cursor_period_end = $cursorPeriodEnd
        running           = $run
        queued            = $q
        lastSeen          = $(if ($kv['lastSeen'] -and $kv['lastSeen'] -ne '-') { [string]$kv['lastSeen'] } else { $null })
        jobs              = $jobs
        source            = 'irc'
    }
    if ($null -ne $remainingPct) {
        $out | Add-Member -NotePropertyName remaining_pct -NotePropertyValue $remainingPct -Force
        $out | Add-Member -NotePropertyName account_remaining_pct -NotePropertyValue $remainingPct -Force
        $out | Add-Member -NotePropertyName cursor_remaining_pct -NotePropertyValue $remainingPct -Force
    }
    return $out
}

function Read-BobIrcPeer {
    param([Parameter(Mandatory)][string]$Id)
    $home = Get-BobIrcHome
    $p = Join-Path $home (Join-Path 'bob-peers' ($Id + '.json'))
    if (-not (Test-Path $p)) { return $null }
    $doc = Read-JsonFile $p
    if (-not $doc -or -not $doc.id) { return $null }
    $jobs = @()
    foreach ($j in @($doc.jobs)) { $jobs += ,$j }
    return [pscustomobject]@{
        ok                = $true
        id                = [string]$doc.id
        lastSeen          = $(if ($doc.lastSeen) { [string]$doc.lastSeen } else { $null })
        hostname          = $null
        jobs              = $jobs
        weekly            = $doc.weekly
        period_end        = $(if ($doc.period_end) { [string]$doc.period_end } else { $null })
        cursor_label      = $(if ($doc.cursor_label) { [string]$doc.cursor_label } else { $null })
        cursor_period_end = $(if ($doc.cursor_period_end) { [string]$doc.cursor_period_end } else { $null })
        repo              = $(if ($doc.repo) { [string]$doc.repo } else { $null })
        kind              = $(if ($doc.kind) { [string]$doc.kind } else { $null })
        model             = $(if ($doc.model) { [string]$doc.model } else { $null })
        sha               = $(if ($doc.sha) { [string]$doc.sha } else { $null })
        source            = $(if ($doc.source) { [string]$doc.source } else { 'irc' })
    }
}

function Get-BobIrcPointDedupeKey {
    param([string]$Line)
    if (-not $Line) { return '' }
    # lastSeen changes every Watch tick; ignore it so identical status does not pile up.
    return ([string]$Line).Trim() -replace '\s+lastSeen=\S+', ''
}

function Test-BobIrcOutboxDuplicatePoint {
    param([string]$Path, [string]$Line)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    $last = $null
    try { $last = Get-Content -LiteralPath $Path -Tail 1 -ErrorAction SilentlyContinue } catch { return $false }
    if (-not $last) { return $false }
    return ((Get-BobIrcPointDedupeKey $last) -eq (Get-BobIrcPointDedupeKey $Line))
}

function Compact-BobIrcOutbox {
    param(
        [string]$Home,
        [int]$ThresholdBytes = 32768
    )
    if (-not $Home) { $Home = Get-BobIrcHome }
    if (-not $Home) { return }
    $outbox = Join-Path $Home 'outbox.txt'
    if (-not (Test-Path -LiteralPath $outbox)) { return }
    $item = Get-Item -LiteralPath $outbox -ErrorAction SilentlyContinue
    if (-not $item -or [int64]$item.Length -le [int64]$ThresholdBytes) { return }
    $lines = @(Get-Content -LiteralPath $outbox -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) { return }
    $points = @($lines | Where-Object { $_ -and ($_ -match 'MOOT v1 POINT' -or $_ -match 'POINT .+BOB v1 ') })
    $other = @($lines | Where-Object { $_ -and $_ -notmatch 'MOOT v1 POINT' -and $_ -notmatch 'POINT .+BOB v1 ' })
    $pointBytes = [Text.Encoding]::UTF8.GetByteCount(($points -join "`n"))
    if ($pointBytes -le $ThresholdBytes) { return }
    $keep = @()
    if ($other.Count -gt 0) { $keep += $other }
    $selfId = $null
    try { $selfId = Get-ThisMachineId } catch { }
    $selfPoints = $points
    if ($selfId) {
        $idRe = 'id=' + [regex]::Escape([string]$selfId) + '\b'
        $mine = @($points | Where-Object { $_ -match $idRe })
        if ($mine.Count -gt 0) { $selfPoints = $mine }
    }
    if ($selfPoints.Count -gt 0) { $keep += $selfPoints[-1] }
    elseif ($points.Count -gt 0) { $keep += $points[-1] }
    Set-Content -LiteralPath $outbox -Value $keep -Encoding utf8
}

function Get-BobIrcTrayPrefix { return 'BOB TRAY v1 ' }

function Test-BobIrcSkipPeerTranscriptOverwrite {
    param($Existing, $Incoming, [Parameter(Mandatory)][string]$ResolvedId)
    $selfId = $null
    try { $selfId = Get-ThisMachineId } catch { }
    if ($selfId -and [string]$ResolvedId -eq [string]$selfId) { return $true }
    if (-not $Existing) { return $false }
    if ([string]$Existing.source -in @('irc-tray', 'irc-digest')) { return $true }
    $exSeen = $null
    $inSeen = $null
    if ($Existing.lastSeen) {
        try {
            $exSeen = [datetime]::Parse([string]$Existing.lastSeen, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        }
        catch { }
    }
    if ($Incoming.lastSeen) {
        try {
            $inSeen = [datetime]::Parse([string]$Incoming.lastSeen, $null, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        }
        catch { }
    }
    if ($exSeen -and $inSeen -and $exSeen -gt $inSeen) { return $true }
    return $false
}

function Test-BobIrcRepoOk {
    param([string]$Repo)
    $s = [string]$Repo
    if (-not $s -or -not $s.Trim()) { return $false }
    return ($s.Trim() -notin @('?', '-', 'irc'))
}

function Get-BobIrcDisplayMachineId {
    param([string]$MachineId)
    $mid = [string]$MachineId
    if ($mid -eq 'ce-priority-dev1') { return 'dev1' }
    return $mid
}

function Get-BobGitShortSha {
    param([string]$Cwd)
    if (-not $Cwd -or -not (Get-Command git -ErrorAction SilentlyContinue)) { return $null }
    try {
        if (-not (Test-Path (Join-Path $Cwd '.git'))) { return $null }
        $sha = & git -C $Cwd rev-parse --short HEAD 2>$null
        if ($sha) { return [string]$sha.Trim() }
    }
    catch { }
    return $null
}

function Get-BobIrcModelFromJob {
    param($Job)
    if (-not $Job) { return $null }
    $fuel = [string]$Job.fuel
    switch ($fuel) {
        'cursor-models' { return 'Cursor Models' }
        'copilot' { return 'Copilot' }
        'grok-bot' { return 'Grok Bot' }
        'grok-build' { return 'grok.exe' }
        'on-demand' { return 'grok.exe' }
    }
    if ($Job.model) { return [string]$Job.model }
    return $null
}

function Get-BobIrcKindFromJob {
    param($Job)
    if (-not $Job) { return $null }
    $k = [string]$Job.kind
    if ($k -eq 'mrb') { return 'mrb' }
    if ($k -eq 'uat') { return 'uat' }
    if ($k -eq 'build') { return 'worker' }
    if ($Job.mrb) { return 'mrb' }
    return $null
}

function Get-BobIrcEffectiveRepo {
    param($Doc, $RunningJob)
    if ($Doc -and (Test-BobIrcRepoOk $Doc.repo)) { return [string]$Doc.repo.Trim() }
    if ($RunningJob -and (Test-BobIrcRepoOk $RunningJob.repo)) { return [string]$RunningJob.repo.Trim() }
    foreach ($j in @($Doc.jobs)) {
        if ($j -and (Test-BobIrcRepoOk $j.repo)) { return [string]$j.repo.Trim() }
    }
    return $null
}

function Get-BobIrcRunningJobFromDoc {
    param($Doc)
    foreach ($j in @($Doc.jobs)) {
        if ($j -and [string]$j.state -eq 'running') { return $j }
    }
    return $null
}

function Get-BobIrcTalkSignature {
    param($Doc)
    if (-not $Doc) { return '' }
    $job = Get-BobIrcRunningJobFromDoc $Doc
    $parts = @(
        [string]$Doc.model
        [string]$Doc.kind
        [string]$Doc.repo
        [string]$Doc.sha
        [string]$Doc.hung
        [string]$Doc.responding
        [string]([int]$Doc.running)
        [string]([int]$Doc.queued)
        [string](Get-BobIrcEffectiveRepo $Doc $job)
    )
    return ($parts -join '|')
}

function Format-BobIrcPeerTalkLine {
    # FR #341: bob-* ears must not announce busy/idle/model/repo status on IRC.
    # Worker state lives only on the digest webhook (Jeeves ACK/DONE). Kept as a
    # no-op so callers and tests still resolve the name.
    param($Doc)
    return $null
}

function Get-BobIrcChangeTalkLine {
    # FR #341: never emit change talk (idle/busy/operational/model/repo) to IRC.
    param($Before, $After)
    return $null
}

function Get-BobIrcWarnStatePath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_irc-warn.json')
}

function Get-BobIrcLongRunningTalkLine {
    # FR #341: long-running warnings are status talk — do not IRC-emit.
    param($Doc, $PrimaryJob)
    return $null
}

function Add-BobIrcOutboxChannelLine {
    param([string]$Line)
    if (-not $Line) { return }
    $home = Get-BobIrcHome
    $outbox = Join-Path $home 'outbox.txt'
    $last = $null
    try { $last = Get-Content -LiteralPath $outbox -Tail 1 -ErrorAction SilentlyContinue } catch { }
    if ($last -and ([string]$last).Trim() -eq [string]$Line.Trim()) { return }
    Add-Content -Path $outbox -Value ([string]$Line).Trim() -Encoding utf8
}

function Add-BobIrcBobiversePrivmsg {
    param([Parameter(Mandatory)][string]$Text)
    $chan = '#bobiverse'
    $safe = ([string]$Text).Trim()
    if (-not $safe) { return }
    Add-BobIrcOutboxChannelLine ("PRIVMSG $chan :$safe")
}

function Invoke-BobIrcDrainOutboxLines {
    param(
        [string[]]$MatchPrefix,
        [string]$SentLogName = 'outbox-drained.txt'
    )
    $home = Get-BobIrcHome
    if (-not $home) { return [pscustomobject]@{ ok = $false; error = 'no_irc_home'; drained = @() } }
    $outbox = Join-Path $home 'outbox.txt'
    if (-not (Test-Path -LiteralPath $outbox)) {
        return [pscustomobject]@{ ok = $true; drained = @() }
    }
    $lines = @(Get-Content -LiteralPath $outbox -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) { return [pscustomobject]@{ ok = $true; drained = @() } }
    $keep = New-Object System.Collections.Generic.List[string]
    $drained = @()
    foreach ($line in $lines) {
        $t = ([string]$line).Trim()
        if (-not $t) { continue }
        $hit = $false
        foreach ($pfx in @($MatchPrefix)) {
            if ($pfx -and $t.StartsWith([string]$pfx)) { $hit = $true; break }
        }
        if ($hit) {
            $drained += $t
        }
        else {
            [void]$keep.Add($t)
        }
    }
    if ($drained.Count -gt 0) {
        Set-Content -LiteralPath $outbox -Value @($keep) -Encoding utf8
        $sentPath = Join-Path $home $SentLogName
        foreach ($d in $drained) { Add-Content -LiteralPath $sentPath -Value $d -Encoding utf8 }
    }
    return [pscustomobject]@{ ok = $true; drained = @($drained) }
}

function Sync-BobIrcChannelOpsWire {
    [CmdletBinding()]
    param()
    $home = Get-BobIrcHome
    if (-not $home) { return [pscustomobject]@{ ok = $false; error = 'no_irc_home' } }
    $path = Join-Path $home 'channel-ops.json'
    $map = Read-JsonFile $path
    if (-not $map) { return [pscustomobject]@{ ok = $false; error = 'no_manifest' } }
    $queued = @()
    if (-not $script:BobChannelOpsWireSent) { $script:BobChannelOpsWireSent = @{} }
    $junk = '[\uFEFF\u200B\u200C\u200D\u2060\u00A0\x00]'
    foreach ($prop in @($map.PSObject.Properties)) {
        # v0.1.19: a BOM / zero-width char in the manifest must never reach the wire as part of a nick.
        $chan = ([regex]::Replace([string]$prop.Name, $junk, '')).Trim()
        $nick = ([regex]::Replace([string]$prop.Value, $junk, '')).Trim().TrimStart(':')
        if (-not $chan -or -not $nick) { continue }
        $line = "MODE $chan +o $nick"
        # Idempotent: the same grant is queued at most once per 15 minutes (the chair also grants it; this is only
        # a fallback), instead of on every manifest sync.
        $prev = $script:BobChannelOpsWireSent[$line]
        if ($prev -and ((Get-Date) - $prev).TotalMinutes -lt 15) { continue }
        $script:BobChannelOpsWireSent[$line] = Get-Date
        Add-BobIrcOutboxChannelLine $line
        $queued += $line
    }
    return [pscustomobject]@{ ok = $true; lines = @($queued) }
}

function ConvertFrom-BobIrcTrayLine {
    param([string]$Text)
    $prefix = Get-BobIrcTrayPrefix
    $raw = ([string]$Text).Trim()
    if (-not $raw.StartsWith($prefix)) { return $null }
    $body = $raw.Substring($prefix.Length).Trim()
    $kv = @{}
    foreach ($tok in $body.Split(' ')) {
        if ($tok -notmatch '=') { return $null }
        $k, $v = $tok.Split('=', 2)
        $kv[$k] = $v
    }
    $mid = [string]$kv['id']
    if (-not $mid -or $mid -eq '-') { return $null }
    if ($mid -notmatch '^[a-z0-9][a-z0-9-]{0,62}$') { return $null }
    $jobs = @()
    $jr = [string]$kv['jobs']
    if ($jr -and $jr -ne '-') {
        foreach ($part in $jr.Split(',')) {
            if ($part -notmatch ':') { continue }
            $repo, $st = $part.Split(':', 2)
            if ((Test-BobIrcRepoOk $repo) -and $st) {
                $jobs += ,[pscustomobject]@{ repo = $repo; state = $st; machine = $mid }
            }
        }
    }
    $weekly = $null
    if ($kv.ContainsKey('weekly') -and [string]$kv['weekly'] -ne '-') {
        try { $weekly = [int]$kv['weekly'] } catch { }
    }
    $repo = $null
    if (Test-BobIrcRepoOk $kv['repo']) { $repo = [string]$kv['repo'] }
    $kind = $null
    if ($kv.ContainsKey('kind') -and [string]$kv['kind'] -ne '-') { $kind = [string]$kv['kind'] }
    $model = $null
    if ($kv.ContainsKey('model') -and [string]$kv['model'] -ne '-') { $model = [string]$kv['model'] }
    return [pscustomobject]@{
        ok         = $true
        id         = $mid
        weekly     = $weekly
        running    = $(try { [int]$kv['running'] } catch { 0 })
        queued     = $(try { [int]$kv['queued'] } catch { 0 })
        lastSeen   = $(if ($kv['lastSeen'] -and $kv['lastSeen'] -ne '-') { [string]$kv['lastSeen'] } else { $null })
        jobs       = $jobs
        repo       = $repo
        kind       = $kind
        model      = $model
        source     = 'irc-tray'
    }
}

function Get-BobIrcTrayLogPosPath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_tray-log.pos')
}

function Get-BobIrcBobiverseLastPath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_bobiverse-last.txt')
}

function Get-BobIrcDigestPrefix { return 'BOB DIGEST v1 ' }

function Get-BobIrcDigestChunkStatePath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_digest-chunks.json')
}

function Test-BobIrcDigestBlobSafe {
    param([string]$Text)
    $lower = ([string]$Text).ToLowerInvariant()
    if (-not $lower) { return $true }
    foreach ($m in @('password=', 'xai_api_key=', 'connect.password', 'bob_report_secret')) {
        if ($lower.Contains($m)) { return $false }
    }
    return $true
}

function Parse-BobIrcDigestWhisperBody {
    param([string]$Body)
    $raw = ([string]$Body).Trim()
    if (-not $raw) { return $null }
    if ($raw.StartsWith('{')) {
        return [pscustomobject]@{ kind = 'json'; text = $raw }
    }
    $prefix = Get-BobIrcDigestPrefix
    if (-not $raw.StartsWith($prefix)) { return $null }
    $rest = $raw.Substring($prefix.Length).Trim()
    if ($rest -match '^(\d+)/(\d+)\s+(.*)$') {
        return [pscustomobject]@{
            kind  = 'chunk'
            index = [int]$Matches[1]
            total = [int]$Matches[2]
            text  = [string]$Matches[3]
        }
    }
    return $null
}

function Read-BobIrcDigestChunkState {
    $p = Get-BobIrcDigestChunkStatePath
    if (-not (Test-Path $p)) {
        return [pscustomobject]@{ total = 0; parts = @{} }
    }
    try {
        $j = Read-JsonFile $p
        $parts = @{}
        if ($j.parts) {
            foreach ($prop in @($j.parts.PSObject.Properties)) {
                $parts[[string]$prop.Name] = [string]$prop.Value
            }
        }
        $total = 0
        try { $total = [int]$j.total } catch { }
        return [pscustomobject]@{ total = $total; parts = $parts }
    }
    catch {
        return [pscustomobject]@{ total = 0; parts = @{} }
    }
}

function Write-BobIrcDigestChunkState {
    param($State)
    $p = Get-BobIrcDigestChunkStatePath
    $dir = Split-Path $p -Parent
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $partsHt = @{}
    foreach ($k in @($State.parts.Keys)) {
        $partsHt[[string]$k] = [string]$State.parts[$k]
    }
    Write-JsonFile $p ([pscustomobject]@{ total = [int]$State.total; parts = $partsHt })
}

function Clear-BobIrcDigestChunkState {
    $p = Get-BobIrcDigestChunkStatePath
    if (Test-Path $p) {
        try { Remove-Item -LiteralPath $p -Force } catch { }
    }
}

function Add-BobIrcDigestChunk {
    param([int]$Index, [int]$Total, [string]$Piece)
    if ($Index -lt 1 -or $Total -lt 1 -or $Index -gt $Total) { return $null }
    $state = Read-BobIrcDigestChunkState
    if ($Index -eq 1 -or $state.total -ne $Total) {
        $state = [pscustomobject]@{ total = $Total; parts = @{} }
    }
    $state.parts[[string]$Index] = [string]$Piece
    $haveAll = $true
    for ($i = 1; $i -le $Total; $i++) {
        if (-not $state.parts.ContainsKey([string]$i)) { $haveAll = $false; break }
    }
    if (-not $haveAll) {
        Write-BobIrcDigestChunkState $state
        return $null
    }
    Clear-BobIrcDigestChunkState
    $sb = New-Object System.Text.StringBuilder
    for ($i = 1; $i -le $Total; $i++) {
        [void]$sb.Append([string]$state.parts[[string]$i])
    }
    return $sb.ToString()
}

function Resolve-BobCursorPoolSeatId {
    param([string]$PoolId)
    $rawId = [string]$PoolId
    if (-not $rawId) { return $null }
    foreach ($seat in @(Get-BobSeatConfig)) {
        if ([string]$seat.id -eq $rawId) { return [string]$seat.id }
        foreach ($sm in @($seat.machines)) {
            if ([string]$sm -eq $rawId) { return [string]$seat.id }
        }
    }
    return $rawId
}

function Normalize-BobCursorSpendingGroupId {
    param([string]$Raw)
    if (-not $Raw) { return 'auto' }
    $s = [string]$Raw.Trim().ToLowerInvariant()
    switch ($s) {
        'grok-chat' { return 'grok-chat' }
        'grok_chat' { return 'grok-chat' }
        'grok-weekly' { return 'grok-chat' }
        'grok_weekly' { return 'grok-chat' }
        'sand' { return 'grok-chat' }
        'high-cost-models' { return 'high-cost-models' }
        'high_cost_models' { return 'high-cost-models' }
        'other-models' { return 'high-cost-models' }
        'other_models' { return 'high-cost-models' }
        'auto' { return 'auto' }
        'low-cost-models' { return 'auto' }
        'low_cost_models' { return 'auto' }
        'cursor-models' { return 'auto' }
        'on-demand' { return 'auto' }
        'ondemand' { return 'auto' }
        'overage' { return 'auto' }
        default {
            if ($s -match 'grok') { return 'grok-chat' }
            if ($s -match 'high|other') { return 'high-cost-models' }
            if ($s -match 'auto|low|cursor|on[- ]?demand|overage|spend') { return 'auto' }
            return 'auto'
        }
    }
}

function Apply-BobIrcDigestCursorPools {
    param($Pools)
    foreach ($pool in @($Pools)) {
        if (-not $pool) { continue }
        $poolId = [string]$pool.id
        if (-not $poolId) { $poolId = [string]$pool.seat }
        if (-not $poolId -and $pool.seat_id) { $poolId = [string]$pool.seat_id }
        $groupId = $null
        if ($pool.group) { $groupId = Normalize-BobCursorSpendingGroupId ([string]$pool.group) }
        elseif ($pool.group_id) { $groupId = Normalize-BobCursorSpendingGroupId ([string]$pool.group_id) }
        # #456 slim rows: group_id alone is enough (no seat id on digest merge pools).
        if (-not $poolId -and -not $groupId) { continue }
        $seatId = $null
        if ($poolId) { $seatId = Resolve-BobCursorPoolSeatId $poolId }
        if (-not $seatId -and $groupId) { $seatId = $groupId }
        if (-not $seatId) { continue }
        $rem = $null
        if ($null -ne $pool.remaining -and [string]$pool.remaining -ne '') {
            try { $rem = [int]$pool.remaining } catch { }
        }
        elseif ($null -ne $pool.remaining_pct -and [string]$pool.remaining_pct -ne '') {
            try { $rem = [int]$pool.remaining_pct } catch { }
        }
        $period = $null
        if ($pool.period_end) { $period = [string]$pool.period_end }
        elseif ($pool.reset) { $period = [string]$pool.reset }
        $label = $null
        if ($pool.group_label) { $label = [string]$pool.group_label }
        elseif ($pool.label) { $label = [string]$pool.label }
        if ($pool.overage) {
            $ov = [string]$pool.overage
            if ($label) { $label = ('{0} {1}' -f $label, $ov) }
            else { $label = $ov }
        }
        if (-not $groupId -and $label) { $groupId = Normalize-BobCursorSpendingGroupId $label }
        # Cursor spending groups are fleet-shared (MarchHare has no local Cursor login).
        # Digest pool ids are cursor-models/other-models/grok-weekly - fan out to every seat.
        $seatTargets = @()
        if ($seatId -match '^(smart-catalogue|club-madeira|ntsa)$') {
            $seatTargets += ,$seatId
        }
        else {
            foreach ($seat in @(Get-BobSeatConfig)) {
                if ($seat -and $seat.id) { $seatTargets += ,[string]$seat.id }
            }
            if ($seatTargets.Count -eq 0 -and $seatId -match '^(smart-catalogue|club-madeira|ntsa)$') {
                $seatTargets += ,$seatId
            }
        }
        foreach ($sid in $seatTargets) {
            if (-not $sid) { continue }
            if ($groupId) {
                Save-BobCursorPoolGroupForSeat -SeatId $sid -GroupId $groupId -RemainingPct $rem -PeriodEnd $period
            }
            # Seat-level period_end is Cursor billing only — never Sand weekly (#456 / FR #448).
            if ($groupId -eq 'low-cost-models' -or $groupId -eq 'auto') {
                Save-BobCursorPoolForSeat -SeatId $sid -RemainingPct $rem -PeriodEnd $period -Label $label
            }
            elseif (-not $groupId) {
                Save-BobCursorPoolForSeat -SeatId $sid -RemainingPct $rem -PeriodEnd $period -Label $label
            }
        }
    }
}

function Get-BobIrcDigestMachinePropertyNames {
    param($Ent)
    if (-not $Ent) { return @() }
    return @($Ent.PSObject.Properties.Name)
}

function Get-BobIrcDigestJobSourcesFromMachine {
    param($Ent)
    if (-not $Ent) { return @() }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    $raw = @()
    if ($names -contains 'jobs') {
        foreach ($j in @($Ent.jobs)) { if ($j) { $raw += ,$j } }
    }
    if ($raw.Count -eq 0 -and ($names -contains 'task') -and $Ent.task) {
        $raw += ,$Ent.task
    }
    return $raw
}

function Test-BobIrcDigestMachineHasJobPayload {
    param($Ent)
    foreach ($j in @(Get-BobIrcDigestJobSourcesFromMachine $Ent)) {
        if (-not $j) { continue }
        if ($j.sha) { return $true }
        if ($j.repo -and (Test-BobIrcRepoOk ([string]$j.repo))) { return $true }
    }
    return $false
}

function Test-BobIrcDigestMachineReportsIdle {
    param($Ent)
    if (-not $Ent) { return $false }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    if ($names -contains 'jobs') {
        foreach ($j in @($Ent.jobs)) {
            if (-not $j) { continue }
            if ($j.sha) { return $false }
            if ($j.repo -and (Test-BobIrcRepoOk ([string]$j.repo))) { return $false }
        }
        return $true
    }
    $run = 0
    $queued = 0
    if ($names -contains 'running') {
        try { $run = [int]$Ent.running } catch { $run = 0 }
    }
    if ($names -contains 'queued') {
        try { $queued = [int]$Ent.queued } catch { $queued = 0 }
    }
    if ($run -le 0 -and $queued -le 0 -and ($names -contains 'running' -or $names -contains 'queued')) {
        return $true
    }
    return $false
}

function ConvertTo-BobDigestCursorPoolRows {
    param(
        $Pools,
        [string]$MachineId = '',
        [string]$Account = '',
        [string]$Channel = ''
    )
    # Slim rows for digest merge / fingerprint (#456): group + remaining + period_end,
    # plus #114 registered account/channel identity the tray needs on each pool row.
    $mid = ''
    if ($MachineId) { $mid = [string]$MachineId.Trim().ToLowerInvariant() }
    $acct = ''
    if ($Account) { $acct = [string]$Account.Trim() }
    elseif ($mid) {
        $acct = Get-BobIrcNick -Config (Get-BobiverseConfig) -MachineId $mid
        if (-not $acct) { $acct = 'bob-' + $mid }
    }
    $chan = ''
    if ($Channel) { $chan = [string]$Channel.Trim() }
    elseif ($mid) { $chan = Get-BobIrcShopChannel -MachineId $mid }
    $rows = @()
    foreach ($p in @($Pools)) {
        if (-not $p) { continue }
        $gid = [string]$p.group_id
        if (-not $gid -and $p.id) { $gid = [string]$p.id }
        if (-not $gid) { continue }
        $rowMid = $mid
        if (-not $rowMid -and $p.machine_id) { $rowMid = [string]$p.machine_id.Trim().ToLowerInvariant() }
        elseif (-not $rowMid -and $p.machine) { $rowMid = [string]$p.machine.Trim().ToLowerInvariant() }
        $rowAcct = $acct
        if (-not $rowAcct -and $p.account) { $rowAcct = [string]$p.account.Trim() }
        elseif (-not $rowAcct -and $p.nick) { $rowAcct = [string]$p.nick.Trim() }
        elseif (-not $rowAcct -and $rowMid) { $rowAcct = 'bob-' + $rowMid }
        $rowChan = $chan
        if (-not $rowChan -and $p.channel) { $rowChan = [string]$p.channel.Trim() }
        elseif (-not $rowChan -and $p.shop) { $rowChan = [string]$p.shop.Trim() }
        elseif (-not $rowChan -and $rowMid) { $rowChan = Get-BobIrcShopChannel -MachineId $rowMid }
        $row = [pscustomobject]@{
            group_id      = $gid
            group_label   = $(if ($p.group_label) { [string]$p.group_label } elseif ($p.label) { [string]$p.label } else { $gid })
            remaining_pct = $p.remaining_pct
            period_end    = $(if ($p.period_end) { [string]$p.period_end } else { $null })
        }
        if ($rowMid) { $row | Add-Member -NotePropertyName machine_id -NotePropertyValue $rowMid -Force }
        if ($rowAcct) { $row | Add-Member -NotePropertyName account -NotePropertyValue $rowAcct -Force }
        if ($rowChan) { $row | Add-Member -NotePropertyName channel -NotePropertyValue $rowChan -Force }
        $rows += ,$row
    }
    return @($rows)
}
function Merge-BobIrcDigestPeerWithPrevious {
    param($Ent, $Doc, $Prev)
    if (-not $Doc -or -not $Prev) { return $Doc }
    if (Test-BobIrcDigestMachineReportsIdle $Ent) {
        $entNames = Get-BobIrcDigestMachinePropertyNames $Ent
        $Doc | Add-Member -NotePropertyName jobs -NotePropertyValue @() -Force
        foreach ($clr in @('repo', 'sha', 'model', 'kind', 'working_on')) {
            if ($Doc.PSObject.Properties.Name -contains $clr) {
                $Doc.$clr = $null
            }
        }
        if ($entNames -contains 'running') {
            try { $Doc | Add-Member -NotePropertyName running -NotePropertyValue ([int]$Ent.running) -Force } catch { }
        }
        if ($entNames -contains 'queued') {
            try { $Doc | Add-Member -NotePropertyName queued -NotePropertyValue ([int]$Ent.queued) -Force } catch { }
        }
        return $Doc
    }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    if ($names -notcontains 'weekly' -and $null -ne $Prev.weekly) {
        $Doc | Add-Member -NotePropertyName weekly -NotePropertyValue $Prev.weekly -Force
    }
    if ($names -notcontains 'period_end' -and -not ($names -contains 'reset' -and $Ent.reset) -and $Prev.period_end) {
        $Doc | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$Prev.period_end) -Force
    }
    if ($names -notcontains 'cursor_label' -and $Prev.cursor_label) {
        $Doc | Add-Member -NotePropertyName cursor_label -NotePropertyValue ([string]$Prev.cursor_label) -Force
    }
    if ($names -notcontains 'cursor_period_end' -and $Prev.cursor_period_end) {
        $Doc | Add-Member -NotePropertyName cursor_period_end -NotePropertyValue ([string]$Prev.cursor_period_end) -Force
    }
    if ($names -notcontains 'sand_period_end' -and $Prev.sand_period_end) {
        $Doc | Add-Member -NotePropertyName sand_period_end -NotePropertyValue ([string]$Prev.sand_period_end) -Force
    }
    if ($names -notcontains 'cursor_pools') {
        $prevPools = @($Prev.cursor_pools)
        if ($prevPools.Count -gt 0) {
            $prevMid = ''
            if ($Doc.id) { $prevMid = [string]$Doc.id }
            elseif ($Prev.id) { $prevMid = [string]$Prev.id }
            $Doc | Add-Member -NotePropertyName cursor_pools -NotePropertyValue @(ConvertTo-BobDigestCursorPoolRows -Pools $prevPools -MachineId $prevMid) -Force
        }
    }
    foreach ($rk in @('remaining_pct', 'account_remaining_pct', 'cursor_remaining_pct')) {
        if ($names -notcontains $rk) {
            $pv = $Prev.$rk
            if ($null -ne $pv -and [string]$pv -ne '') {
                try { $Doc | Add-Member -NotePropertyName $rk -NotePropertyValue ([int]$pv) -Force } catch { }
            }
        }
    }
    if (-not (Test-BobIrcDigestMachineHasJobPayload $Ent)) {
        $prevJobs = @()
        foreach ($j in @($Prev.jobs)) { if ($j) { $prevJobs += ,$j } }
        if ($prevJobs.Count -gt 0) {
            $Doc | Add-Member -NotePropertyName jobs -NotePropertyValue $prevJobs -Force
        }
    }
    foreach ($fld in @('sha', 'repo', 'model', 'kind')) {
        if ($names -notcontains $fld) {
            $pv = $Prev.$fld
            if ($pv -and -not $Doc.$fld) {
                $Doc | Add-Member -NotePropertyName $fld -NotePropertyValue ([string]$pv) -Force
            }
        }
    }
    return $Doc
}

function ConvertTo-BobIrcPeerFromDigestMachine {
    param([string]$MachineId, $Ent)
    if (-not $Ent) { return $null }
    $mid = Resolve-BobiverseMachineId $MachineId
    if (-not $mid) { return $null }
    $jobs = @()
    foreach ($j in @(Get-BobIrcDigestJobSourcesFromMachine $Ent)) {
        if (-not $j) { continue }
        $repo = $null
        if ($j.repo -and (Test-BobIrcRepoOk ([string]$j.repo))) { $repo = [string]$j.repo }
        $st = 'running'
        if ($j.state) { $st = [string]$j.state }
        $row = [pscustomobject]@{
            repo        = $repo
            state       = $st
            machine     = $mid
            sha         = $(if ($j.sha) { [string]$j.sha } else { $null })
            model       = $(if ($j.model) { [string]$j.model } else { $null })
            description = $(if ($j.description) { [string]$j.description } else { $null })
            run_time    = $(if ($j.run_time) { [string]$j.run_time } else { $null })
        }
        if ($repo -or $row.sha) { $jobs += ,$row }
    }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    $weekly = $null
    if ($names -contains 'weekly' -and $null -ne $Ent.weekly -and [string]$Ent.weekly -ne '') {
        try { $weekly = [int]$Ent.weekly } catch { }
    }
    $periodEnd = $null
    if ($Ent.period_end) { $periodEnd = [string]$Ent.period_end }
    elseif ($Ent.reset) { $periodEnd = [string]$Ent.reset }
    $primaryJob = Get-BobIrcDigestTaskFromJobs @(Get-BobIrcDigestJobSourcesFromMachine $Ent)
    $topRepo = $null
    if ($names -contains 'repo' -and $Ent.repo -and (Test-BobIrcRepoOk ([string]$Ent.repo))) { $topRepo = [string]$Ent.repo }
    elseif ($primaryJob -and $primaryJob.repo -and (Test-BobIrcRepoOk ([string]$primaryJob.repo))) {
        $topRepo = [string]$primaryJob.repo
    }
    $topSha = $null
    if ($names -contains 'sha' -and $Ent.sha) { $topSha = [string]$Ent.sha }
    elseif ($primaryJob -and $primaryJob.sha) { $topSha = [string]$primaryJob.sha }
    $topModel = $null
    if ($names -contains 'model' -and $Ent.model) { $topModel = [string]$Ent.model }
    elseif ($primaryJob -and $primaryJob.model) { $topModel = [string]$primaryJob.model }
    $workerCount = 0
    if ($names -contains 'workers' -and $null -ne $Ent.workers -and [string]$Ent.workers -ne '') {
        if ($Ent.workers -is [System.Array] -or ($Ent.workers -is [System.Collections.IEnumerable] -and $Ent.workers -isnot [string])) {
            $workerCount = @($Ent.workers).Count
        }
        else {
            try { $workerCount = [int]$Ent.workers } catch { $workerCount = 0 }
        }
    }
    $runFlag = 0
    try { $runFlag = [int]$Ent.running } catch { }
    return [pscustomobject]@{
        ok                = $true
        id                = $mid
        weekly            = $weekly
        period_end        = $periodEnd
        cursor_label      = $(if ($names -contains 'cursor_label' -and $Ent.cursor_label) { [string]$Ent.cursor_label } else { $null })
        cursor_period_end = $(if ($names -contains 'cursor_period_end' -and $Ent.cursor_period_end) { [string]$Ent.cursor_period_end } else { $null })
        sand_period_end   = $(if ($names -contains 'sand_period_end' -and $Ent.sand_period_end) { [string]$Ent.sand_period_end } else { $null })
        cursor_pools      = $(if ($names -contains 'cursor_pools' -and $Ent.cursor_pools) { @(ConvertTo-BobDigestCursorPoolRows -Pools @($Ent.cursor_pools) -MachineId $mid) } else { @() })
        remaining_pct     = $(if ($names -contains 'remaining_pct' -and $null -ne $Ent.remaining_pct -and [string]$Ent.remaining_pct -ne '') { try { [int]$Ent.remaining_pct } catch { $null } } else { $null })
        account_remaining_pct = $(if ($names -contains 'account_remaining_pct' -and $null -ne $Ent.account_remaining_pct -and [string]$Ent.account_remaining_pct -ne '') { try { [int]$Ent.account_remaining_pct } catch { $null } } elseif ($names -contains 'remaining_pct' -and $null -ne $Ent.remaining_pct -and [string]$Ent.remaining_pct -ne '') { try { [int]$Ent.remaining_pct } catch { $null } } else { $null })
        cursor_remaining_pct  = $(if ($names -contains 'cursor_remaining_pct' -and $null -ne $Ent.cursor_remaining_pct -and [string]$Ent.cursor_remaining_pct -ne '') { try { [int]$Ent.cursor_remaining_pct } catch { $null } } elseif ($names -contains 'remaining_pct' -and $null -ne $Ent.remaining_pct -and [string]$Ent.remaining_pct -ne '') { try { [int]$Ent.remaining_pct } catch { $null } } else { $null })
        running           = $(try { [int]$Ent.running } catch { 0 })
        queued            = $(try { [int]$Ent.queued } catch { 0 })
        lastSeen          = $(if ($Ent.lastSeen) { [string]$Ent.lastSeen } else { $null })
        jobs              = $jobs
        model             = $topModel
        kind              = $(if ($names -contains 'kind' -and $Ent.kind) { [string]$Ent.kind } else { $null })
        repo              = $topRepo
        sha               = $topSha
        fuel              = $(if ($Ent.fuel) { [string]$Ent.fuel } else { $null })
        source            = 'irc-digest'
    }
}

function Get-BobIrcDigestTaskFromJobs {
    param($Jobs)
    foreach ($j in @($Jobs)) {
        if (-not $j) { continue }
        $st = [string]$j.state
        if ($st -match '^(?i)(running|start|queued)$') { return $j }
    }
    if (@($Jobs).Count -gt 0) { return $Jobs[0] }
    return $null
}

function Get-BobIrcDigestSyntheticTaskFromMachine {
    param($Ent)
    if (-not $Ent) { return $null }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    $workerCount = 0
    if ($names -contains 'workers' -and $null -ne $Ent.workers -and [string]$Ent.workers -ne '') {
        if ($Ent.workers -is [System.Array] -or ($Ent.workers -is [System.Collections.IEnumerable] -and $Ent.workers -isnot [string])) {
            $workerCount = @($Ent.workers).Count
        }
        else {
            try { $workerCount = [int]$Ent.workers } catch { }
        }
    }
    $runFlag = 0
    try { $runFlag = [int]$Ent.running } catch { }
    if ($workerCount -le 0 -and $runFlag -le 0) { return $null }
    $desc = 'irc agent'
    if ($names -contains 'working_on' -and $Ent.working_on) { $desc = [string]$Ent.working_on }
    return [pscustomobject]@{
        repo        = 'irc'
        sha         = $null
        model       = $(if ($workerCount -gt 0) { ('workers={0}' -f $workerCount) } else { 'running' })
        description = $desc
        run_time    = $null
        state       = 'START'
    }
}

function Get-BobIrcDigestReportPatchFromMachine {
    param($Ent)
    if (-not $Ent) { return $null }
    $names = Get-BobIrcDigestMachinePropertyNames $Ent
    $node = [ordered]@{}
    $primary = Get-BobIrcDigestTaskFromJobs @(Get-BobIrcDigestJobSourcesFromMachine $Ent)
    if (-not $primary) { $primary = Get-BobIrcDigestSyntheticTaskFromMachine $Ent }
    if ($primary) {
        $node.task = [pscustomobject]@{
            repo        = $(if ($primary.repo) { [string]$primary.repo } else { $null })
            sha         = $(if ($primary.sha) { [string]$primary.sha } else { $null })
            model       = $(if ($primary.model) { [string]$primary.model } else { $null })
            description = $(if ($primary.description) { [string]$primary.description } else { $null })
            run_time    = $(if ($primary.run_time) { [string]$primary.run_time } else { $null })
            state       = $(if ($primary.state) { [string]$primary.state } else { 'START' })
        }
    }
    if ($names -contains 'pcent' -and $Ent.pcent) { $node.pcent = $Ent.pcent }
    if ($names -contains 'uptime_since' -and $Ent.uptime_since) {
        $node.uptime_since = [string]$Ent.uptime_since
    }
    if ($node.Count -eq 0) { return $null }
    return [pscustomobject]$node
}

function Build-BobIrcReportDigestFromBobiverse {
    param($DigestObj)
    $prev = Read-BobReportDigest
    $machinesOut = [ordered]@{}
    if ($prev -and $prev.machines) {
        foreach ($p in @($prev.machines.PSObject.Properties)) {
            $machinesOut[[string]$p.Name] = $p.Value
        }
    }
    $nodes = $DigestObj.machines
    if (-not $nodes) {
        if ($machinesOut.Count -gt 0) {
            return [pscustomobject]@{ machines = [pscustomobject]$machinesOut }
        }
        return [pscustomobject]@{ machines = [pscustomobject]@{} }
    }
    $anyPatch = $false
    foreach ($prop in @($nodes.PSObject.Properties)) {
        $mid = Resolve-BobiverseMachineId ([string]$prop.Name)
        if (-not $mid) { continue }
        $ent = $prop.Value
        if (-not $ent) { continue }
        $patch = Get-BobIrcDigestReportPatchFromMachine $ent
        if (-not $patch) { continue }
        $anyPatch = $true
        $merged = [ordered]@{}
        $existing = $null
        if ($machinesOut.Contains($mid)) { $existing = $machinesOut[$mid] }
        if ($existing) {
            if ($existing.task) { $merged.task = $existing.task }
            if ($existing.pcent) { $merged.pcent = $existing.pcent }
            if ($existing.uptime_since) { $merged.uptime_since = [string]$existing.uptime_since }
        }
        if ($patch.task) {
            $keepExisting = $false
            if ($existing -and $existing.task) {
                $exSha = [string]$existing.task.sha
                $ptSha = [string]$patch.task.sha
                if ($exSha -and -not $ptSha) { $keepExisting = $true }
                elseif ($exSha -and $ptSha -and $exSha -ne $ptSha) {
                    if ($patch.task.repo -eq 'irc' -and $existing.task.repo -ne 'irc') { $keepExisting = $true }
                }
            }
            if (-not $keepExisting) { $merged.task = $patch.task }
        }
        if ($patch.pcent) { $merged.pcent = $patch.pcent }
        $patchNames = Get-BobIrcDigestMachinePropertyNames $ent
        if ($patchNames -contains 'uptime_since' -and $patch.uptime_since) {
            $merged.uptime_since = [string]$patch.uptime_since
        }
        $machinesOut[$mid] = [pscustomobject]$merged
    }
    if (-not $anyPatch -and $prev) { return $prev }
    return [pscustomobject]@{ machines = [pscustomobject]$machinesOut }
}

function Import-BobIrcDigestJson {
    param($DigestObj)
    if (-not $DigestObj) { return @() }
    $home = Get-BobIrcHome
    $dir = Join-Path $home 'bob-peers'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $updated = @()
    if ($DigestObj.cursor_pools) {
        Apply-BobIrcDigestCursorPools -Pools @($DigestObj.cursor_pools)
    }
    $report = Build-BobIrcReportDigestFromBobiverse -DigestObj $DigestObj
    Write-JsonFile (Join-Path $dir '_report-digest.json') $report
    $nodes = $DigestObj.machines
    if (-not $nodes) { return $updated }
    foreach ($prop in @($nodes.PSObject.Properties)) {
        $doc = ConvertTo-BobIrcPeerFromDigestMachine -MachineId ([string]$prop.Name) -Ent $prop.Value
        if (-not $doc) { continue }
        # #456: per-machine pools (when chair persists them) — apply group period_ends.
        if ($doc.cursor_pools -and @($doc.cursor_pools).Count -gt 0) {
            Apply-BobIrcDigestCursorPools -Pools @($doc.cursor_pools)
        }
        $resolved = [string]$doc.id
        Save-BobIrcChairDigestPeer -MachineId $resolved -ChairPeer $doc
        $peerPath = Join-Path $dir ($resolved + '.json')
        $prev = $null
        if (Test-Path $peerPath) {
            try { $prev = Read-JsonFile $peerPath } catch { }
        }
        if ($prev) {
            $doc = Merge-BobIrcDigestPeerWithPrevious -Ent $prop.Value -Doc $doc -Prev $prev
        }
        Save-BobSeatPeriodEnd -MachineId $resolved -PeriodEnd $(if ($doc.period_end) { [string]$doc.period_end } else { $null }) -Weekly $doc.weekly
        if ($doc.cursor_label -and [string]$doc.cursor_label -ne 'empty') {
            $seat = Get-BobSeatForMachine -MachineId $resolved
            if ($seat) {
                Save-BobCursorPoolForSeat -SeatId ([string]$seat.id) -Label ([string]$doc.cursor_label) -PeriodEnd $(if ($doc.cursor_period_end) { [string]$doc.cursor_period_end } else { $null })
            }
        }
        Write-JsonFile $peerPath $doc
        $updated += $resolved
    }
    return $updated
}

function Import-BobIrcDigestWhisperBody {
    param([string]$Body)
    $parsed = Parse-BobIrcDigestWhisperBody $Body
    if (-not $parsed) { return @() }
    $jsonText = $null
    if ($parsed.kind -eq 'json') {
        $jsonText = [string]$parsed.text
    }
    elseif ($parsed.kind -eq 'chunk') {
        $jsonText = Add-BobIrcDigestChunk -Index $parsed.index -Total $parsed.total -Piece ([string]$parsed.text)
    }
    if (-not $jsonText) { return @() }
    if (-not (Test-BobIrcDigestBlobSafe $jsonText)) { return @() }
    try {
        $obj = $jsonText | ConvertFrom-Json
    }
    catch { return @() }
    return @(Import-BobIrcDigestJson -DigestObj $obj)
}

function Test-BobIrcBobiversePullSeat {
    # bob-* builders on Watch-Bobiverse only (#196). Talk seats and shop workers never pull.
    if ($env:BOB_IRC_SKIP_BOBIVERSE_PULL -eq '1') { return $false }
    $cfg = Get-BobiverseConfig
    if ($cfg -and $cfg.chairNick) {
        $cn = [string]$cfg.chairNick
        if ($cn.Trim()) {
            $active = $null
            if ($env:BOB_IRC_NICK -and $env:BOB_IRC_NICK.Trim()) { $active = $env:BOB_IRC_NICK.Trim() }
            else {
                $id = Get-ThisMachineId
                if ($id) { $active = Get-BobIrcNick $cfg $id }
            }
            if ($active -and $active -eq $cn.Trim()) { return $false }
        }
    }
    $id = Get-ThisMachineId
    $nick = $null
    if ($env:BOB_IRC_NICK -and $env:BOB_IRC_NICK.Trim()) { $nick = $env:BOB_IRC_NICK.Trim() }
    elseif ($cfg -and $id) { $nick = Get-BobIrcNick $cfg $id }
    if (-not $nick) { return $false }
    $nl = $nick.ToLowerInvariant()
    if ($nl -match '^w-[a-z0-9]+-\d+$') { return $false }
    foreach ($mid in @(Get-BobiverseMachineIds)) {
        $ml = $mid.ToLowerInvariant()
        if ($nl -eq $ml -or $nl -match ('^' + [regex]::Escape($ml) + '-\d+$')) { return $false }
    }
    if ($cfg -and $cfg.nicks) {
        foreach ($p in @($cfg.nicks.PSObject.Properties)) {
            if ([string]$p.Value -eq $nick) { return $true }
        }
    }
    if ($nl -match '^bob-') {
        $tail = $nl.Substring(4)
        if (Resolve-BobiverseMachineId $tail) { return $true }
    }
    return $false
}

function Get-BobIrcChairDigestPeersPath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_chair-digest-peers.json')
}

function Save-BobIrcChairDigestPeer {
    param(
        [string]$MachineId,
        [Parameter(Mandatory)]$ChairPeer
    )
    $mid = Resolve-BobiverseMachineId $MachineId
    if (-not $mid -or -not $ChairPeer) { return }
    $p = Get-BobIrcChairDigestPeersPath
    $map = @{}
    if (Test-Path -LiteralPath $p) {
        try {
            $j = Read-JsonFile $p
            foreach ($prop in @($j.PSObject.Properties)) {
                $map[[string]$prop.Name] = $prop.Value
            }
        }
        catch { }
    }
    $map[$mid] = $ChairPeer
    try { Write-JsonFile $p ([pscustomobject]$map) } catch { }
}

function Get-BobIrcChairDigestPeerForMachine {
    param([string]$MachineId)
    $mid = Resolve-BobiverseMachineId $MachineId
    if (-not $mid) { return $null }
    $p = Get-BobIrcChairDigestPeersPath
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    try {
        $j = Read-JsonFile $p
        if (-not $j) { return $null }
        $peer = $j.$mid
        if (-not $peer) { return $null }
        return $peer
    }
    catch { return $null }
}

function Sync-BobDigestWebhookAfterBobiversePull {
    param([Parameter(Mandatory)]$LocalDoc)
    if (-not $LocalDoc) { return }
    $mid = [string]$LocalDoc.id
    if (-not $mid) { return }
    $chair = Get-BobIrcChairDigestPeerForMachine -MachineId $mid
    Send-BobDigestWebhookIfChanged -Doc $LocalDoc -Before $chair | Out-Null
}

function Request-BobIrcBobiversePull {
    param([int]$MinIntervalSec = 60)
    if (-not (Test-BobIrcBobiversePullSeat)) { return $false }
    $stampPath = Get-BobIrcBobiverseLastPath
    $now = [DateTime]::UtcNow
    if (Test-Path $stampPath) {
        try {
            $prev = [datetime]::Parse((Get-Content $stampPath -Raw).Trim(), $null, [Globalization.DateTimeStyles]::RoundtripKind)
            if (($now - $prev.ToUniversalTime()).TotalSeconds -lt $MinIntervalSec) { return $false }
        }
        catch { }
    }
    # Prefer HTTP digest GET (#174/#179). Do not PRIVMSG !bobiverse.
    $doc = $null
    try { $doc = Read-BobReportDigestHttp } catch { $doc = $null }
    if (-not $doc) {
        try { $doc = Read-BobReportDigest } catch { $doc = $null }
    }
    if ($doc) {
        try {
            Import-BobIrcDigestJson -DigestObj $doc | Out-Null
        } catch {
            # Best-effort ingest; still stamp so we do not spam.
        }
    }
    Set-Content -Path $stampPath -Value $now.ToString('o') -Encoding utf8 -NoNewline
    return [bool]$doc
}


function Import-BobIrcTrayPull {
    $home = Get-BobIrcHome
    $logPath = Join-Path $home 'irc.log'
    if (-not (Test-Path $logPath)) { return @() }
    $posPath = Get-BobIrcTrayLogPosPath
    $pos = 0
    if (Test-Path $posPath) {
        try { $pos = [int64](Get-Content $posPath -Raw).Trim() } catch { $pos = 0 }
    }
    # FR #355: FileStream seek+read instead of ReadAllBytes + $bytes[$pos..end] (O(n) copy).
    $fs = $null
    $len = 0L
    $text = ''
    try {
        $fs = [IO.File]::Open($logPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $len = [int64]$fs.Length
        if ($pos -gt $len) { $pos = 0 }
        $toRead = [int]([Math]::Min([int64]([int]::MaxValue), ($len - $pos)))
        if ($toRead -gt 0) {
            $null = $fs.Seek($pos, [IO.SeekOrigin]::Begin)
            $buf = New-Object byte[] $toRead
            $got = $fs.Read($buf, 0, $toRead)
            if ($got -gt 0) {
                if ($got -lt $buf.Length) { [Array]::Resize([ref]$buf, $got) }
                $text = [Text.Encoding]::UTF8.GetString($buf)
            }
        }
    }
    finally {
        if ($fs) { $fs.Dispose() }
    }
    $nick = $null
    try {
        $cfg = Get-BobiverseConfig
        $id = Get-ThisMachineId
        if ($cfg -and $id) { $nick = Get-BobIrcNick $cfg $id }
    }
    catch { }
    if (-not $nick -and $env:BOB_IRC_NICK -and $env:BOB_IRC_NICK.Trim()) {
        $nick = $env:BOB_IRC_NICK.Trim()
    }
    if (-not $nick) {
        try {
            $id = Get-ThisMachineId
            if ($id) { $nick = 'bob-' + $id }
        }
        catch { }
    }
    if (-not $nick) { return @() }
    $nickEsc = [regex]::Escape($nick)
    $updated = @()
    $dir = Join-Path $home 'bob-peers'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $trayPrefix = Get-BobIrcTrayPrefix
    $digestPrefix = Get-BobIrcDigestPrefix
    foreach ($line in @($text -split "`n")) {
        $t = $line.Trim()
        if (-not $t) { continue }
        if ($t -notmatch "(?i)PRIVMSG\s+$nickEsc\s+:(?<ircbody>.*)$") { continue }
        $body = [string]$Matches['ircbody'].Trim()
        if ($body.StartsWith($digestPrefix) -or $body.StartsWith('{')) {
            foreach ($id in @(Import-BobIrcDigestWhisperBody $body)) {
                if ($id -and $updated -notcontains $id) { $updated += $id }
            }
            continue
        }
        if (-not $body.StartsWith($trayPrefix)) { continue }
        $doc = ConvertFrom-BobIrcTrayLine $body
        if (-not $doc) { continue }
        $resolved = Resolve-BobiverseMachineId ([string]$doc.id)
        if (-not $resolved) { continue }
        $doc | Add-Member -NotePropertyName id -NotePropertyValue $resolved -Force
        $peerPath = Join-Path $dir ($resolved + '.json')
        if (-not $doc.period_end -and (Test-Path $peerPath)) {
            try {
                $prev = Read-JsonFile $peerPath
                if ($prev -and $prev.period_end) {
                    $doc | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$prev.period_end) -Force
                }
                if ($prev -and $prev.cursor_label -and -not $doc.cursor_label) {
                    $doc | Add-Member -NotePropertyName cursor_label -NotePropertyValue ([string]$prev.cursor_label) -Force
                }
                if ($prev -and $prev.cursor_period_end -and -not $doc.cursor_period_end) {
                    $doc | Add-Member -NotePropertyName cursor_period_end -NotePropertyValue ([string]$prev.cursor_period_end) -Force
                }
            }
            catch { }
        }
        Save-BobSeatPeriodEnd -MachineId $resolved -PeriodEnd $(if ($doc.period_end) { [string]$doc.period_end } else { $null }) -Weekly $doc.weekly
        $prevTray = $null
        if (Test-Path $peerPath) {
            try { $prevTray = Read-JsonFile $peerPath } catch { }
        }
        $doc = Merge-BobIrcPeerRemaining -Prev $prevTray -Incoming $doc
        Write-JsonFile $peerPath $doc
        $updated += $resolved
    }
    Set-Content -Path $posPath -Value $len -Encoding utf8 -NoNewline
    return $updated
}

function Get-BobDigestWebhookPostStatePath {
    Join-Path (Get-BobIrcHome) (Join-Path 'bob-peers' '_digest-webhook-posted.json')
}

function Get-BobDigestWebhookCapturePath {
    # FR #113: hermetic Assert uses BOB_DIGEST_WEBHOOK_CAPTURE; also honour BOB_DIGEST_CAPTURE.
    foreach ($name in @('BOB_DIGEST_WEBHOOK_CAPTURE', 'BOB_DIGEST_CAPTURE')) {
        $v = [string][Environment]::GetEnvironmentVariable($name)
        if ($v -and $v.Trim()) { return $v.Trim() }
    }
    return ''
}

function Get-BobDigestReportUrl {
    $cfg = Get-BobiverseConfig
    $url = ''
    if ($cfg -and $cfg.reportUrl) { $url = [string]$cfg.reportUrl }
    if (-not $url.Trim()) { $url = [string]$env:BOB_REPORT_URL }
    $url = $url.Trim()
    if ($url) { return $url }
    return $null
}

function Get-BobDigestWebhookJobsFingerprint {
    param($Doc)
    $jobsNorm = @()
    foreach ($j in @($Doc.jobs)) {
        if (-not $j) { continue }
        $jobsNorm += ,([ordered]@{ repo = [string]$j.repo; state = [string]$j.state })
    }
    if ($jobsNorm.Count -eq 0) { return '[]' }
    return ($jobsNorm | ConvertTo-Json -Compress -Depth 4)
}

function Test-BobIrcDigestWebhookChairInSync {
    param($Chair, $Local)
    if (-not $Chair -or -not $Local) { return $false }
    if ([string]$Chair.source -ne 'irc-digest') {
        return (Get-BobDigestWebhookFingerprint $Chair) -eq (Get-BobDigestWebhookFingerprint $Local)
    }
    if ([int]$Chair.running -ne [int]$Local.running) { return $false }
    if ([int]$Chair.queued -ne [int]$Local.queued) { return $false }
    if ($null -ne $Chair.weekly -and [string]$Chair.weekly -ne '' -and [string]$Chair.weekly -ne [string]$Local.weekly) {
        return $false
    }
    foreach ($rk in @('remaining_pct', 'account_remaining_pct', 'cursor_remaining_pct')) {
        $cv = $Chair.$rk
        $lv = $Local.$rk
        if ($null -eq $cv -or [string]$cv -eq '') { continue }
        if ($null -eq $lv -or [string]$lv -eq '') { return $false }
        if ([int]$cv -ne [int]$lv) { return $false }
    }
    if ($Chair.cursor_label -and [string]$Chair.cursor_label -ne '' -and [string]$Chair.cursor_label -ne [string]$Local.cursor_label) {
        return $false
    }
    if ($Chair.cursor_period_end -and [string]$Chair.cursor_period_end -ne [string]$Local.cursor_period_end) { return $false }
    if ($Chair.sand_period_end -and [string]$Chair.sand_period_end -ne [string]$Local.sand_period_end) { return $false }
    if ($Chair.period_end -and [string]$Chair.period_end -ne [string]$Local.period_end) { return $false }
    # #456: per-pool remaining + period_end must stay in sync (Sand weekly vs billing).
    if ($Chair.cursor_pools -or $Local.cursor_pools) {
        $chairPools = Get-BobDigestWebhookPoolSnapshot -Pools @(ConvertTo-BobDigestCursorPoolRows -Pools @($Chair.cursor_pools))
        $localPools = Get-BobDigestWebhookPoolSnapshot -Pools @(ConvertTo-BobDigestCursorPoolRows -Pools @($Local.cursor_pools))
        if ($chairPools -ne $localPools) { return $false }
    }
    if ($Chair.model -and [string]$Chair.model -ne [string]$Local.model) { return $false }
    if ($Chair.kind -and [string]$Chair.kind -ne [string]$Local.kind) { return $false }
    if ($Chair.repo -and [string]$Chair.repo -ne [string]$Local.repo) { return $false }
    if ($Chair.sha -and [string]$Chair.sha -ne [string]$Local.sha) { return $false }
    if ($Chair.fuel -and [string]$Chair.fuel -ne [string]$Local.fuel) { return $false }
    if ($Chair.working_on -and [string]$Chair.working_on -ne [string]$Local.working_on) { return $false }
    if ($null -ne $Chair.online -and [string]$Chair.online -ne [string]$Local.online) { return $false }
    if ($Chair.status -and [string]$Chair.status -ne [string]$Local.status) { return $false }
    if ($null -ne $Chair.responding -and [string]$Chair.responding -ne [string]$Local.responding) { return $false }
    $chairJobs = @($Chair.jobs)
    $localJobs = @($Local.jobs)
    if ($chairJobs.Count -gt 0 -or $localJobs.Count -gt 0) {
        $chairFp = Get-BobDigestWebhookJobsFingerprint $Chair
        $localFp = Get-BobDigestWebhookJobsFingerprint $Local
        if ($chairFp -ne $localFp) { return $false }
    }
    return $true
}

function Get-BobDigestWebhookFingerprint {
    param($Doc)
    if (-not $Doc) { return '' }
    $jobsNorm = @()
    foreach ($j in @($Doc.jobs)) {
        if (-not $j) { continue }
        $jobsNorm += ,([ordered]@{ repo = [string]$j.repo; state = [string]$j.state })
    }
    $jobsJson = '[]'
    if ($jobsNorm.Count -gt 0) {
        $jobsJson = ($jobsNorm | ConvertTo-Json -Compress -Depth 4)
    }
    $poolsSig = ''
    if ($Doc.cursor_pools) {
        $poolsSig = Get-BobDigestWebhookPoolSnapshot -Pools @(ConvertTo-BobDigestCursorPoolRows -Pools @($Doc.cursor_pools))
    }
    $parts = @(
        [string]([int]$Doc.running)
        [string]([int]$Doc.queued)
        [string]$Doc.weekly
        [string]$Doc.cursor_label
        [string]$Doc.cursor_period_end
        [string]$Doc.sand_period_end
        [string]$Doc.period_end
        [string]$Doc.model
        [string]$Doc.kind
        [string]$Doc.repo
        [string]$Doc.sha
        [string]$Doc.fuel
        [string]$Doc.working_on
        [string]$Doc.online
        [string]$Doc.status
        [string]$Doc.responding
        [string]$Doc.remaining_pct
        [string]$Doc.overage_gbp
        [string]$Doc.overage_usd
        [string]$Doc.overspend_state
        [string]$Doc.on_demand_limit_cents
        $(if ($Doc.pcent) { ($Doc.pcent | ConvertTo-Json -Compress -Depth 5) } else { '' })
        $poolsSig
        $jobsJson
    )
    return ($parts -join '|')
}

function Build-BobDigestWebhookMergePayload {
    param($Doc)
    $id = [string]$Doc.id
    if (-not $id) { return $null }
    $payload = [ordered]@{
        op      = 'merge'
        machine = $id
        online  = $true
        status  = 'operational'
    }
    # Report lastSeen only advances when the merge carries it (heartbeat).
    if ($Doc.lastSeen) { $payload.lastSeen = [string]$Doc.lastSeen }
    if ($null -ne $Doc.weekly -and [string]$Doc.weekly -ne '') { $payload.weekly = [int]$Doc.weekly }
    if ($Doc.cursor_label) { $payload.cursor_label = [string]$Doc.cursor_label }
    if ($Doc.cursor_period_end) { $payload.cursor_period_end = [string]$Doc.cursor_period_end }
    # #456: Sand / grok-chat weekly reset — distinct from Cursor billingCycleEnd.
    if ($Doc.sand_period_end) { $payload.sand_period_end = [string]$Doc.sand_period_end }
    if ($Doc.period_end) { $payload.period_end = [string]$Doc.period_end }
    if ($Doc.model) { $payload.model = [string]$Doc.model }
    if ($Doc.kind) { $payload.kind = [string]$Doc.kind }
    if ($Doc.repo) { $payload.repo = [string]$Doc.repo }
    if ($Doc.sha) { $payload.sha = [string]$Doc.sha }
    if ($Doc.fuel) { $payload.fuel = $Doc.fuel }
    # FR #356 (agentic_build): seat start reports pool|session-key|unknown (never the key)
    if ($Doc.fuel_mode) { $payload.fuel_mode = [string]$Doc.fuel_mode }
    if ($Doc.working_on) { $payload.working_on = [string]$Doc.working_on }
    if ($null -ne $Doc.running) { $payload.running = [int]$Doc.running }
    if ($null -ne $Doc.queued) { $payload.queued = [int]$Doc.queued }
    if ($Doc.jobs -and @($Doc.jobs).Count -gt 0) { $payload.jobs = @($Doc.jobs) }
    if ($Doc.pcent) { $payload.pcent = $Doc.pcent }
    # #456: each Bob reports per-pool remaining + period_end (grok-chat weekly vs high/auto billing).
    if ($Doc.cursor_pools) {
        $docMid = ''
        if ($Doc.id) { $docMid = [string]$Doc.id }
        $poolRows = @(ConvertTo-BobDigestCursorPoolRows -Pools @($Doc.cursor_pools) -MachineId $docMid)
        if ($poolRows.Count -gt 0) { $payload.cursor_pools = @($poolRows) }
    }
    # CAST IRON (Simon 2026-09-27): month overspend GBP on every usage heartbeat.
    if ($null -ne $Doc.overage_gbp -and [string]$Doc.overage_gbp -ne '') {
        try { $payload.overage_gbp = [double]$Doc.overage_gbp } catch { }
    }
    # #60: overspend amount + state (none|over|at-limit|unknown) so the digest/tray can show it per machine.
    if ($null -ne $Doc.overage_usd -and [string]$Doc.overage_usd -ne '') {
        try { $payload.overage_usd = [double]$Doc.overage_usd } catch { }
    }
    if ($Doc.overspend_state) { $payload.overspend_state = [string]$Doc.overspend_state }
    foreach ($odk in @('on_demand_used_cents', 'on_demand_limit_cents', 'on_demand_remaining_pct')) {
        $odv = $Doc.$odk
        if ($null -ne $odv -and [string]$odv -ne '') { try { $payload[$odk] = [int]$odv } catch { } }
    }
    return [pscustomobject]$payload
}

function Test-BobDigestWebhookPayloadSecretFree {
    param([string]$Json)
    if (-not $Json) { return $true }
    $lower = $Json.ToLowerInvariant()
    foreach ($m in @('password=', 'xai_api_key=', 'x-bob-secret', 'report.secret', 'connect.password', 'bob_report_secret')) {
        if ($lower.Contains($m)) { return $false }
    }
    return $true
}

# Named *MergePost* (not Invoke-BobDigestWebhookPost): Invoke-BobDigestWebhook.ps1
# defines Invoke-BobDigestWebhookPost(-WorkingOn/-Repo) and is dot-sourced later,
# so a same-named function here was silently replaced and every -Payload caller
# threw "A parameter cannot be found that matches parameter name 'Payload'".
function Invoke-BobDigestWebhookMergePost {
    param([Parameter(Mandatory)]$Payload)
    $capture = Get-BobDigestWebhookCapturePath
    $body = $Payload | ConvertTo-Json -Depth 8 -Compress
    if (-not (Test-BobDigestWebhookPayloadSecretFree $body)) { return $null }
    if ($capture) {
        $capDir = Split-Path $capture -Parent
        if ($capDir -and -not (Test-Path $capDir)) {
            New-Item -ItemType Directory -Force -Path $capDir | Out-Null
        }
        Add-Content -LiteralPath $capture -Value $body -Encoding utf8
        return 204
    }
    $url = Get-BobDigestReportUrl
    if (-not $url) { return $null }
    # v0.1.16: NO password/secret. The digest accepts this machine because Jeeves published it on the
    # ChanServ roster (registered-machines.json); the receiver validates + rate-limits instead.
    try {
        $resp = Invoke-WebRequest -Uri $url -Method POST -Body $body -ContentType 'application/json' `
            -UseBasicParsing -TimeoutSec 15
        return [int]$resp.StatusCode
    }
    catch {
        if ($_.Exception.Response) {
            try { return [int]$_.Exception.Response.StatusCode.value__ } catch { }
        }
        return $null
    }
}

function Get-BobDigestWebhookHeartbeatSec {
    # Change-only POSTs never advance report lastSeen while a peer is idle and in
    # sync. Re-POST at most this often (0 disables). Env: BOB_DIGEST_WEBHOOK_HEARTBEAT_SEC.
    # #41: every bob reports its Grok + Cursor pools about every 30 s (tray PollSec = 30);
    # the digest merge is idempotent (fingerprint compare) so an unchanged re-POST is a no-op.
    $raw = [string]$env:BOB_DIGEST_WEBHOOK_HEARTBEAT_SEC
    if ($raw.Trim()) {
        try { return [int]$raw.Trim() } catch { }
    }
    return 30
}

function Test-BobDigestWebhookHeartbeatDue {
    param(
        [hashtable]$Posted,
        [string]$MachineId,
        [string]$StatePath
    )
    $sec = Get-BobDigestWebhookHeartbeatSec
    if ($sec -le 0 -or -not $MachineId -or -not $Posted) { return $false }
    # Never posted for this machine: normal change detection handles the first POST.
    if (-not $Posted.ContainsKey($MachineId)) { return $false }
    $last = $null
    $atKey = $MachineId + '@posted_at'
    if ($Posted.ContainsKey($atKey)) {
        try { $last = [DateTimeOffset]::FromUnixTimeSeconds([long]$Posted[$atKey]).UtcDateTime } catch { }
    }
    if ($null -eq $last -and $StatePath -and (Test-Path -LiteralPath $StatePath)) {
        # State written before posted_at existed: fall back to file mtime.
        try { $last = (Get-Item -LiteralPath $StatePath).LastWriteTimeUtc } catch { }
    }
    if ($null -eq $last) { return $true }
    return (([DateTime]::UtcNow - $last).TotalSeconds -ge $sec)
}

function Send-BobDigestWebhookIfChanged {
    param(
        [Parameter(Mandatory)]$Doc,
        $Before
    )
    $mid = [string]$Doc.id
    if (-not $mid) { return $null }
    $capture = Get-BobDigestWebhookCapturePath
    $posted = @{}
    $statePath = Get-BobDigestWebhookPostStatePath
    if (Test-Path $statePath) {
        try {
            $j = Read-JsonFile $statePath
            foreach ($p in @($j.PSObject.Properties)) { $posted[[string]$p.Name] = [string]$p.Value }
        }
        catch { }
    }
    # FR #113: capture mode is for Assert/hermetic tests — always write the ndjson line
    # (do not skip on fingerprint / heartbeat / chair-in-sync).
    $forceCapture = [bool]$capture
    $heartbeatDue = Test-BobDigestWebhookHeartbeatDue -Posted $posted -MachineId $mid -StatePath $statePath
    if (-not $forceCapture -and -not $heartbeatDue -and $Before) {
        if (Test-BobIrcDigestWebhookChairInSync -Chair $Before -Local $Doc) {
            return $null
        }
    }
    $fp = Get-BobDigestWebhookFingerprint $Doc
    if (-not $forceCapture -and -not $heartbeatDue -and $posted.ContainsKey($mid) -and [string]$posted[$mid] -eq $fp) { return $null }
    if (-not (Get-BobDigestReportUrl) -and -not $capture) {
        return $null
    }
    $payload = Build-BobDigestWebhookMergePayload $Doc
    if (-not $payload) { return $null }
    $code = Invoke-BobDigestWebhookMergePost -Payload $payload
    if ($null -ne $code -and $code -ge 200 -and $code -lt 300) {
        $posted[$mid] = $fp
        $posted[$mid + '@posted_at'] = [string]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
        try { Write-JsonFile $statePath ([pscustomobject]$posted) } catch { }
        return $code
    }
    return $null
}

function Write-BobIrcStatus {
    param(
        [switch]$SkipDigestWebhook,
        [switch]$PassThru
    )
    $id = Get-ThisMachineId
    if (-not $id) { return }
    $cfg = Get-BobiverseConfig
    if (-not $cfg) { return }
    $home = Get-BobIrcHome
    $bridge = Get-BridgeRoot
    $running = Filter-BobFleetLaneJobsLive -Jobs (Get-BobPeerLaneJobs -BridgeRoot $bridge -MachineId $id -Lane running -StampRepo)
    $inbox = Filter-BobFleetLaneJobsLive -Jobs (Get-BobPeerLaneJobs -BridgeRoot $bridge -MachineId $id -Lane inbox -StampRepo)
    $jobs = @()
    foreach ($j in @($running)) {
        $repo = Get-BobJobRepoStamp $j
        if (Test-BobIrcRepoOk $repo) {
            $jobs += ,[pscustomobject]@{ repo = $repo; state = 'running' }
        }
    }
    foreach ($j in @($inbox)) {
        $repo = Get-BobJobRepoStamp $j
        if (Test-BobIrcRepoOk $repo) {
            $jobs += ,[pscustomobject]@{ repo = $repo; state = 'queued' }
        }
    }
    $primary = $null
    if (@($running).Count -gt 0) { $primary = $running[0] }
    $liveN = 0
    foreach ($g in @(Get-BobLiveGrokAgents)) {
        $liveN++
        $repo = 'grok.exe'
        if ($g.cwd) {
            $slug = Get-GitHubSlugFromCwd $g.cwd
            if ($slug -and $slug -ne '?' -and $slug -ne $env:USERNAME) { $repo = $slug }
        }
        if (Test-BobIrcRepoOk $repo) {
            $jobs += ,[pscustomobject]@{ repo = $repo; state = 'running' }
        }
        if (-not $primary) { $primary = $g }
    }
    $week = $null
    $periodEnd = $null
    try {
        $w = Get-BobWeeklyRemaining
        if ($w -and $null -ne $w.remaining_pct) { $week = [int]$w.remaining_pct }
        if ($w -and $w.period_end) { $periodEnd = [string]$w.period_end }
    }
    catch { }
    $seen = [DateTime]::UtcNow.ToString('o')
    Save-BobSeatPeriodEnd -MachineId $id -PeriodEnd $periodEnd -Weekly $week -ClearWeekly:([bool]($w -and $w.stale))
    $cursorLabel = $null
    $cursorPeriodEnd = $null
    $sandPeriodEnd = $null
    $cursorRemainingPct = $null
    $overageGbp = $null
    $cw = $null
    try {
        $cw = Get-BobCursorAgentWeeklyRemaining
        if ($cw) {
            if ($null -ne $cw.remaining_pct) { $cursorRemainingPct = [int]$cw.remaining_pct }
            $cursorLabel = Format-BobCursorAccountLabel -RemainingPct $cw.remaining_pct -UsedPct $cw.used_pct
            try { $overageGbp = Get-BobCursorOverageGbp } catch { }
            if ($null -eq $overageGbp -and $null -ne $cw.overage_gbp) { $overageGbp = [double]$cw.overage_gbp }
            if ($cursorLabel -eq 'empty') {
                if ($null -ne $overageGbp) { $cursorLabel = ('-{0}{1:N2}' -f [char]0x00A3, [math]::Abs([double]$overageGbp)) }
            }
            if ($cw.period_end) { $cursorPeriodEnd = [string]$cw.period_end }
            # #456: Sand / grok-chat weekly reset (never Cursor billingCycleEnd).
            if ($cw.sand_period_end) { $sandPeriodEnd = [string]$cw.sand_period_end }
            if ($cursorLabel -and $cursorLabel -ne 'empty') {
                Save-BobCursorAccountCache -Label $cursorLabel -PeriodEnd $cursorPeriodEnd
            }
        }
    } catch { }
    $model = Get-BobIrcModelFromJob $primary
    if (-not $model -and $cursorLabel -and $cursorLabel -ne 'empty') { $model = 'Cursor Models' }
    $kind = Get-BobIrcKindFromJob $primary
    $topRepo = $null
    if ($primary) { $topRepo = Get-BobJobRepoStamp $primary }
    if (-not (Test-BobIrcRepoOk $topRepo)) { $topRepo = $null }
    $sha = $null
    if ($primary -and $primary.cwd) { $sha = Get-BobGitShortSha ([string]$primary.cwd) }
    $responding = $null
    if ($primary -and $primary.sessionId) {
        try { $responding = Test-BobJobProcess -SessionId ([string]$primary.sessionId) } catch { }
    }
    $startedAt = $null
    if ($primary) {
        if ($primary.claimedAt) { $startedAt = [string]$primary.claimedAt }
        elseif ($primary.createdAt) { $startedAt = [string]$primary.createdAt }
    }
    $pcent = $null
    try {
        if ($cw -and $cw.cursor_spending_groups) {
            $pcentMap = [ordered]@{}
            foreach ($g in @($cw.cursor_spending_groups)) {
                if (-not $g) { continue }
                $gid = [string]$g.id
                if (-not $gid) { continue }
                $key = $gid
                if ($gid -eq 'auto' -or $gid -eq 'low-cost-models') { $key = 'cursor-models' }
                elseif ($gid -eq 'high-cost-models') { $key = 'high-cost-models' }
                elseif ($gid -eq 'grok-chat') { $key = 'grok-chat' }
                if ($null -ne $g.remaining_pct -and [string]$g.remaining_pct -ne '') {
                    $pcentMap[$key] = [int]$g.remaining_pct
                }
            }
            if ($null -ne $cw.sand_remaining_pct -and [string]$cw.sand_remaining_pct -ne '') {
                $pcentMap['grok-chat'] = [int]$cw.sand_remaining_pct
            }
            if ($null -ne $cw.on_demand_remaining_pct -and [string]$cw.on_demand_remaining_pct -ne '') {
                $pcentMap['on-demand'] = [int]$cw.on_demand_remaining_pct
            }
            if ($pcentMap.Count -gt 0) { $pcent = [pscustomobject]$pcentMap }
        }
    } catch { $pcent = $null }
    $doc = [pscustomobject]@{
        ok                     = $true
        id                     = $id
        online                 = $true
        status                 = 'operational'
        weekly                 = $week
        period_end             = $periodEnd
        cursor_label           = $cursorLabel
        cursor_period_end      = $cursorPeriodEnd
        sand_period_end        = $sandPeriodEnd
        remaining_pct          = $cursorRemainingPct
        account_remaining_pct  = $cursorRemainingPct
        cursor_remaining_pct   = $cursorRemainingPct
        overage_gbp            = $overageGbp
        overage_usd            = $(if ($cw) { $cw.overage_usd } else { $null })
        overspend_state        = $(if ($cw) { $cw.overspend_state } else { $null })
        on_demand_used_cents   = $(if ($cw) { $cw.on_demand_used_cents } else { $null })
        on_demand_limit_cents  = $(if ($cw) { $cw.on_demand_limit_cents } else { $null })
        on_demand_remaining_pct = $(if ($cw) { $cw.on_demand_remaining_pct } else { $null })
        pcent                  = $pcent
        running                = @($running).Count + $liveN
        queued                 = @($inbox).Count
        lastSeen               = $seen
        jobs                   = $jobs
        model                  = $model
        kind                   = $kind
        repo                   = $topRepo
        sha                    = $sha
        started_at             = $startedAt
        responding             = $responding
        source                 = 'irc'
    }
    try {
        # FR #445 / #456: publish only this host's pools (never peer/fleet values as own).
        # Each pool carries its own period_end (grok-chat = Sand weekly; high/auto = billing).
        $poolRows = @(Get-BobCursorPoolsForTray -MachineId $id -LocalCursorDoc $cw -PcentRows @() -LocalOnly)
        # #114: stamp registered bob account + shop channel on each pool row.
        $poolAccount = Get-BobIrcNick -Config $cfg -MachineId $id
        if (-not $poolAccount) { $poolAccount = 'bob-' + $id }
        $slimPools = @(ConvertTo-BobDigestCursorPoolRows -Pools $poolRows -MachineId $id -Account $poolAccount -Channel (Get-BobIrcShopChannel -MachineId $id))
        if ($slimPools.Count -gt 0) {
            $doc | Add-Member -NotePropertyName cursor_pools -NotePropertyValue @($slimPools) -Force
            # #41: when cursor_spending_groups was unavailable (pcent empty - e.g. marchhare), derive
            # this machine's pcent from its own pool rows so the digest still gets grok-chat / cursor bars.
            if ($null -eq $doc.pcent -or @($doc.pcent.PSObject.Properties).Count -eq 0) {
                $fromRows = [ordered]@{}
                foreach ($pr in $slimPools) {
                    if ($null -eq $pr.remaining_pct -or [string]$pr.remaining_pct -eq '') { continue }
                    $k = switch ([string]$pr.group_id) {
                        'auto'             { 'cursor-models' }
                        'low-cost-models'  { 'cursor-models' }
                        default            { [string]$pr.group_id }
                    }
                    try { $fromRows[$k] = [int]$pr.remaining_pct } catch { }
                }
                if ($fromRows.Count -gt 0) { $doc.pcent = [pscustomobject]$fromRows }
            }
            Save-BobFleetCursorPoolsSnapshot -MachineId $id -Pools @($slimPools)
            $localSeat = Get-BobSeatForMachine -MachineId $id
            if ($localSeat -and $localSeat.id) {
                foreach ($pr in $slimPools) {
                    Save-BobCursorPoolGroupForSeat -SeatId ([string]$localSeat.id) -GroupId ([string]$pr.group_id) `
                        -RemainingPct $pr.remaining_pct -PeriodEnd $(if ($pr.period_end) { [string]$pr.period_end } else { $null })
                }
            }
        }
    }
    catch { }
    $dir = Join-Path $home 'bob-peers'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $peerPath = Join-Path $dir ($id + '.json')
    $before = $null
    if (Test-Path $peerPath) {
        try { $before = Read-JsonFile $peerPath } catch { }
    }
    Write-JsonFile $peerPath $doc
    # FR #341: never append idle/busy/operational/long-running status to outbox.
    # Keep peer JSON + digest webhook only (Jeeves owns worker busy/idle via ACK/DONE).
    if (-not $SkipDigestWebhook) {
        Send-BobDigestWebhookIfChanged -Doc $doc -Before $before | Out-Null
    }
    if ($PassThru) { return $doc }
}

function Import-BobIrcPeerTranscript {
    $cfg = Get-BobiverseConfig
    if (-not $cfg) { return @() }
    $home = Get-BobIrcHome
    $mid = [string]$cfg.mootId
    if (-not $mid) { return @() }
    $tp = Join-Path $home (Join-Path 'moot' ($mid + '.txt'))
    if (-not (Test-Path $tp)) { return @() }

    # FR #355: skip when size+mtime unchanged (paid every ~30s tick otherwise).
    $item = Get-Item -LiteralPath $tp -ErrorAction SilentlyContinue
    if (-not $item) { return @() }
    $sig = '{0}|{1}' -f $item.Length, $item.LastWriteTimeUtc.Ticks
    if (-not $script:BobIrcPeerTranscriptCache) {
        $script:BobIrcPeerTranscriptCache = @{}
    }
    $cacheKey = $tp.ToLowerInvariant()
    if ($script:BobIrcPeerTranscriptCache.ContainsKey($cacheKey)) {
        $hit = $script:BobIrcPeerTranscriptCache[$cacheKey]
        if ($hit -and [string]$hit.sig -eq $sig) {
            return @()
        }
    }

    # Last POINT per machine wins (append-only). Walk newest-first; cheap id= skim
    # then full parse only once per raw id (ionos: 64s → ~0.4s).
    $lines = @(Get-Content -LiteralPath $tp -ErrorAction SilentlyContinue)
    $latest = @{}
    $seenRaw = @{}
    $idRx = [regex]'BOB v1 id=(\S+)'
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        $raw = [string]$lines[$i]
        if ($raw -notmatch 'POINT' -or $raw -notmatch 'BOB v1 ') { continue }
        $m = $idRx.Match($raw)
        if (-not $m.Success) { continue }
        $rawId = [string]$m.Groups[1].Value
        if (-not $rawId) { continue }
        if ($seenRaw.ContainsKey($rawId)) { continue }
        $seenRaw[$rawId] = $true
        $idx = $raw.IndexOf('BOB v1 ')
        if ($idx -lt 0) { continue }
        $doc = ConvertFrom-BobIrcPoint $raw.Substring($idx)
        if (-not $doc) { continue }
        $resolved = Resolve-BobiverseMachineId ([string]$doc.id)
        if (-not $resolved) { continue }
        if ($latest.ContainsKey($resolved)) { continue }
        $doc | Add-Member -NotePropertyName id -NotePropertyValue $resolved -Force
        $latest[$resolved] = $doc
    }

    $updated = @()
    $dir = Join-Path $home 'bob-peers'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    foreach ($resolved in @($latest.Keys)) {
        $doc = $latest[$resolved]
        $peerPath = Join-Path $dir ($resolved + '.json')
        $prev = $null
        if (Test-Path $peerPath) {
            try { $prev = Read-JsonFile $peerPath } catch { }
        }
        if (Test-BobIrcSkipPeerTranscriptOverwrite -Existing $prev -Incoming $doc -ResolvedId $resolved) { continue }
        # Keep prior period_end when the latest POINT still lacks reset=.
        if (-not $doc.period_end -and $prev -and $prev.period_end) {
            $doc | Add-Member -NotePropertyName period_end -NotePropertyValue ([string]$prev.period_end) -Force
        }
        Save-BobSeatPeriodEnd -MachineId $resolved -PeriodEnd $(if ($doc.period_end) { [string]$doc.period_end } else { $null }) -Weekly $doc.weekly
        if ($doc.cursor_label -and [string]$doc.cursor_label -ne 'empty') {
            Save-BobCursorAccountCache -Label ([string]$doc.cursor_label) -PeriodEnd $(if ($doc.cursor_period_end) { [string]$doc.cursor_period_end } else { $null })
        }
        $doc = Merge-BobIrcPeerRemaining -Prev $prev -Incoming $doc
        Write-JsonFile $peerPath $doc
        $updated += $resolved
    }
    $script:BobIrcPeerTranscriptCache[$cacheKey] = [pscustomobject]@{ sig = $sig; at = [datetime]::UtcNow }
    return $updated
}
