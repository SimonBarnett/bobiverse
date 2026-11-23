# BobTrayStartWorker.ps1 - tray side of "!startworker" (t810u). Dot-sourced by Watch-BobTray.ps1.
#
# The ear (service, session 0) authorises/caps/queues a request file; the tray - the one process that lives in the
# interactive session - launches the worker through the SAME function as the Agent / Plan click. Protocol (common\scripts\startworker.py):
#   <root>\run\startworker\tray.alive     heartbeat (FR #2697: ThreadPool host timer / System.Timers.Timer every ~2 s; may include engine_last_tick)
#   <root>\run\startworker\engine.alive   FR #4136/#4317: written by Watch-BobTray at the START of each startworker tick
#   <root>\run\startworker\req-<id>.json  {id, mode, by, kind, ts, expires}  written atomically by the ear
#   <root>\run\startworker\res-<id>.json  {id, ok, reason, pid}               audit trail written here
# A request is DELETED before it is acted on (at-most-once) and ignored once expired. No credentials in any file.

function Get-BobTrayStartWorkerDir {
    param([Parameter(Mandatory)][string]$Root)
    return (Join-Path (Join-Path $Root 'run') 'startworker')
}

function Get-BobTraySeatTarget {
    <#
    FR #7669: per-machine seat target in the bridge config.json (read every call).
    Missing key means the normal target. 0 means seats are off on this machine.
    #>
    $bridgeHome = $env:BOB_BRIDGE_HOME
    if (-not $bridgeHome -or -not $bridgeHome.Trim()) {
        $bridgeHome = Join-Path $env:USERPROFILE '.grok\bob-bridge'
    }
    $cfg = Join-Path $bridgeHome 'config.json'
    if (-not (Test-Path -LiteralPath $cfg)) { return $null }
    try {
        $j = Get-Content -LiteralPath $cfg -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($j.PSObject.Properties.Name -notcontains 'seat_target') { return $null }
        return [int]$j.seat_target
    } catch { return $null }
}

function Test-BobTraySeatsOff {
    $t = Get-BobTraySeatTarget
    return ($null -ne $t -and [int]$t -eq 0)
}

function Test-BobTrayEmptyOnlineDisabled {
    <#
    FR #9142 / #9240: operator kill switch without seat_target=0.
    Presence of <root>\run\startworker\empty-online.disabled skips every auto
    seat-start path (empty-online fill, under-cap fill, startworker kind=auto,
    recycle restore). TipForm Agents / Workers clicks and explicit !startworker
    (non-auto req) still work.
    #>
    param([Parameter(Mandatory)][string]$Root)
    $dir = Get-BobTrayStartWorkerDir -Root $Root
    return (Test-Path -LiteralPath (Join-Path $dir 'empty-online.disabled') -PathType Leaf)
}

function Test-BobTraySeatStartTriggerIsManual {
    <#
    FR #9346 / #9240: TipForm click and explicit !startworker triggers only.
    Fail-closed: anything else (other, empty, unknown, auto-start, restore-*,
    empty-online, under-cap, engine-restart, ...) is treated as automatic.
    #>
    param([string]$Trigger = '')
    $t = ([string]$Trigger).Trim().ToLowerInvariant()
    if (-not $t) { return $false }
    if ($t -eq 'menu' -or $t -eq 'jeeves-menu' -or $t -eq 'startworker') { return $true }
    if ($t.StartsWith('workers-')) { return $true }
    return $false
}

function Test-BobTraySeatStartTriggerIsAuto {
    <#
    FR #9240 / #9346: tray/chair auto paths (auto-start, restore-after-recycle,
    empty-online, under-cap, other, unknown). Fail-closed — not an explicit
    TipForm / !startworker trigger means auto (blocked when empty-online.disabled).
    #>
    param([string]$Trigger = '')
    return -not [bool](Test-BobTraySeatStartTriggerIsManual -Trigger $Trigger)
}

function Test-BobTrayEmptyOnlineBlocksAutoStart {
    <#
    FR #9240 / #9346: true when empty-online.disabled is present AND Trigger is
    not an explicit manual TipForm / !startworker trigger (fail-closed).
    Manual TipForm triggers (menu, workers-*, jeeves-menu) and explicit
    startworker stay false (allowed).
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Trigger = ''
    )
    if (-not (Test-BobTrayEmptyOnlineDisabled -Root $Root)) { return $false }
    return [bool](Test-BobTraySeatStartTriggerIsAuto -Trigger $Trigger)
}

function Write-BobTrayUnrequestedSeatStartIntake {
    <#
    FR #9240: deduped intake when an auto seat start is attempted (or refused)
    while empty-online.disabled is present. Stamp
    run/startworker/unrequested-start.intake — one filing per 6h per machine.
    Returns $true when a filing was attempted, $false when skipped (dedup / error).
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Trigger = 'auto-start',
        [string]$Site = 'Start-BobTrayWorkerExe'
    )
    try {
        $dir = Get-BobTrayStartWorkerDir -Root $Root
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        $stamp = Join-Path $dir 'unrequested-start.intake'
        if (Test-Path -LiteralPath $stamp) {
            $ageH = ([datetime]::UtcNow - (Get-Item -LiteralPath $stamp).LastWriteTimeUtc).TotalHours
            if ($ageH -ge 0 -and $ageH -lt 6) { return $false }
        }
        $trig = ([string]$Trigger -replace '[^A-Za-z0-9._-]', '')
        if (-not $trig) { $trig = 'auto-start' }
        $siteSafe = ([string]$Site -replace '[^A-Za-z0-9._-]', '')
        if (-not $siteSafe) { $siteSafe = 'tray' }
        $title = 'Tray auto seat start while empty-online.disabled (FR #9240)'
        $body = @"
Unrequested tray seat-start attempt while run/startworker/empty-online.disabled is present.

trigger=$trig
site=$siteSafe
root=$Root

Standing rule: seats start only from TipForm clicks (or explicit !startworker).
Auto paths (empty-online fill, under-cap, kind=auto startworker, recycle restore) must refuse.
"@
        Set-Content -LiteralPath $stamp -Value ([datetime]::UtcNow.ToString('o')) -Encoding ASCII
        $report = $null
        foreach ($rel in @(
                'common\scripts\Report-BobiverseIntakeIssue.ps1',
                'scripts\Report-BobiverseIntakeIssue.ps1'
            )) {
            $cand = Join-Path $Root $rel
            if (Test-Path -LiteralPath $cand) { $report = $cand; break }
        }
        if ($report) {
            try {
                & $report -Repo 'SimonBarnett/bobiverse' -Kind issue -Title $title -Body $body | Out-Null
            } catch { }
        }
        return $true
    } catch {
        return $false
    }
}

function Get-BobTrayEmptyOnlineFillCount {
    <#
    FR #8429: an online shop with zero agent seats should be filled to the hard cap.
    FR #3180 still owns a partial heal (1 of 2). Seats-off, a pending req, or a
    recent fill stamp means do not write another request.
    FR #9142: -Disabled (empty-online.disabled) also returns 0 without seats-off.
    #>
    param(
        [int]$LiveAgents = 0,
        [int]$PendingReqs = 0,
        [bool]$SeatsOff = $false,
        [bool]$Cooldown = $false,
        [int]$Cap = 2,
        [bool]$Disabled = $false
    )
    if ($Disabled -or $SeatsOff -or $Cooldown) { return 0 }
    if ($LiveAgents -gt 0 -or $PendingReqs -gt 0) { return 0 }
    if ($Cap -lt 1) { return 0 }
    return [Math]::Min([int]$Cap, 2)
}

function Get-BobTrayCachedOpencodeFreeRemaining {
    <#
    FR #9000: TipForm/hover snapshot free % only. Never invent a number.
    #>
    $snap = $script:lastFuelSnapshot
    if (-not $snap) { return $null }
    foreach ($k in @('opencode_free', 'opencode-free')) {
        if ($snap.PSObject.Properties.Name -contains $k -and $null -ne $snap.$k -and [string]$snap.$k -ne '') {
            try { return [int]$snap.$k } catch { }
        }
    }
    return $null
}

function Get-BobTrayEmptyOnlineFillAgentChoice {
    <#
    FR #9000: when grok weekly remaining is known 0, empty-online fill pins
    agent=opencode slot=free so auto does not burn the 2-seat cap on hard-402.
    Unknown grok remaining keeps auto (skip=false, agent empty).
    FR #9142 / #9023: when grok is known 0 and opencode free is not viable
    (known free 0, or no free leaf), return skip=true reason=no-fuel instead of
    falling through to kind=auto -> Grok zombies. Menu/auto elsewhere unchanged.
    Does not invent fuel numbers.
    #>
    param(
        $GrokRemaining,
        $OpencodeFreeRemaining,
        [string]$Root = ''
    )
    $auto = [pscustomobject]@{ agent = ''; slot = ''; skip = $false; reason = '' }
    $nofuel = [pscustomobject]@{ agent = ''; slot = ''; skip = $true; reason = 'no-fuel' }
    if (-not $PSBoundParameters.ContainsKey('GrokRemaining')) {
        $GrokRemaining = $null
        if (Get-Command Get-BobTrayGrokFuelRemaining -ErrorAction SilentlyContinue) {
            try { $GrokRemaining = Get-BobTrayGrokFuelRemaining } catch { $GrokRemaining = $null }
        }
    }
    if ($null -eq $GrokRemaining -or [string]$GrokRemaining -eq '') {
        return $auto
    }
    try { $g = [int]$GrokRemaining } catch {
        return $auto
    }
    if ($g -ne 0) {
        return $auto
    }

    if (-not $PSBoundParameters.ContainsKey('OpencodeFreeRemaining')) {
        $OpencodeFreeRemaining = Get-BobTrayCachedOpencodeFreeRemaining
    }
    if ($null -ne $OpencodeFreeRemaining -and [string]$OpencodeFreeRemaining -ne '') {
        try {
            if ([int]$OpencodeFreeRemaining -lt 1) {
                return $nofuel
            }
        } catch { }
    }

    $leaf = ''
    if (Get-Command Resolve-BobTrayOpencodeSlotModel -ErrorAction SilentlyContinue) {
        try { $leaf = [string](Resolve-BobTrayOpencodeSlotModel -Root $Root -Slot 'free') } catch { $leaf = '' }
    }
    if (-not $leaf) {
        return $nofuel
    }
    return [pscustomobject]@{ agent = 'opencode'; slot = 'free'; skip = $false; reason = 'opencode-free' }
}

function Get-BobTrayUnderCapFillCount {
    <#
      FR #8890: one busy seat is not a full shop. When offerable work remains
      and live agent seats are below the hard cap, ask for one more seat.
      Zero live seats stay on Get-BobTrayEmptyOnlineFillCount.
      FR #9195: -Disabled (empty-online.disabled) also returns 0 (no under-cap auto starts).
    #>
    param(
        [int]$LiveAgents = 0,
        [int]$PendingReqs = 0,
        [bool]$SeatsOff = $false,
        [bool]$Cooldown = $false,
        [int]$Cap = 2,
        [int]$Offerable = 0,
        [bool]$Disabled = $false
    )
    if ($Disabled -or $SeatsOff -or $Cooldown -or $PendingReqs -gt 0) { return 0 }
    if ($Offerable -lt 1 -or $LiveAgents -lt 1 -or $Cap -lt 1) { return 0 }
    if ($LiveAgents -ge $Cap) { return 0 }
    return 1
}

function Get-BobTrayCachedOfferableCount {
    $paths = @()
    if (Get-Command Get-BobIrcHome -ErrorAction SilentlyContinue) {
        $paths += (Join-Path (Get-BobIrcHome) 'bob-peers\_report-digest.json')
    }
    foreach ($p in $paths) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        try {
            $j = Get-Content -LiteralPath $p -Raw -ErrorAction Stop | ConvertFrom-Json
            if ($null -ne $j.offerable_count) { return [int]$j.offerable_count }
            if ($j.queue -and $null -ne $j.queue.offerable_count) { return [int]$j.queue.offerable_count }
        } catch { }
    }
    return 0
}

function Get-BobTrayDigestMachineWorkerCount {
    <#
    FR #9462: count live workers on a digest/report machine node.
    Returns $null when the workers shape is unknown (do not alert).
    #>
    param($Ent)
    if (-not $Ent) { return $null }
    $names = @()
    try { $names = @($Ent.PSObject.Properties.Name) } catch { $names = @() }
    if ($names -contains 'worker_list' -and $null -ne $Ent.worker_list) {
        return @($Ent.worker_list).Count
    }
    if ($names -contains 'workers') {
        $w = $Ent.workers
        if ($null -eq $w) { return 0 }
        # Nick-map digest shape is a Hashtable/Dictionary — use .Count (not PSObject.Properties).
        if ($w -is [System.Collections.IDictionary]) {
            return [int]$w.Count
        }
        if ($w -is [System.Collections.IList] -and -not ($w -is [string])) {
            return @($w).Count
        }
        try {
            $props = @($w.PSObject.Properties)
            return $props.Count
        } catch { return 0 }
    }
    return $null
}

function Get-BobTrayOnlineZeroWorkerAlerts {
    <#
    FR #9462: durable TipForm/Status alerts when an online machine (local or
    fleet peer on the digest) has zero workers while offerable_count > 0.
    Alert only - never silent auto-start (FR #3180); operator uses TipForm Agents.
    #>
    param(
        $Machines,
        [int]$OfferableCount = 0
    )
    if ($OfferableCount -lt 1) { return @() }
    $alerts = New-Object System.Collections.Generic.List[string]
    $entries = @()
    if ($null -eq $Machines) { return @() }
    if ($Machines -is [System.Collections.IDictionary]) {
        foreach ($k in @($Machines.Keys)) {
            $entries += [pscustomobject]@{ id = [string]$k; ent = $Machines[$k] }
        }
    } elseif ($Machines.PSObject -and $Machines.PSObject.Properties) {
        $looksLikeTiles = $false
        foreach ($p in @($Machines.PSObject.Properties)) {
            $v = $p.Value
            $vNames = @()
            try { if ($v) { $vNames = @($v.PSObject.Properties.Name) } } catch { $vNames = @() }
            if ($v -and ($vNames -contains 'online' -or $vNames -contains 'workers' -or $vNames -contains 'worker_list')) {
                $entries += [pscustomobject]@{ id = [string]$p.Name; ent = $v }
            } else {
                $looksLikeTiles = $true
            }
        }
        if ($entries.Count -eq 0 -and $looksLikeTiles) {
            foreach ($m in @($Machines)) {
                if (-not $m) { continue }
                $entries += [pscustomobject]@{ id = [string]$m.id; ent = $m }
            }
        }
    } else {
        foreach ($m in @($Machines)) {
            if (-not $m) { continue }
            $mid = $null
            try { $mid = [string]$m.id } catch { $mid = $null }
            if (-not $mid) { try { $mid = [string]$m.machine } catch { $mid = $null } }
            $entries += [pscustomobject]@{ id = $mid; ent = $m }
        }
    }
    foreach ($row in $entries) {
        $mid = [string]$row.id
        $ent = $row.ent
        if (-not $mid -or -not $ent) { continue }
        $online = $false
        $entNames = @()
        try { $entNames = @($ent.PSObject.Properties.Name) } catch { $entNames = @() }
        try {
            if ($entNames -contains 'online' -and $null -ne $ent.online) { $online = [bool]$ent.online }
            elseif ($entNames -contains 'reach') {
                $online = ([string]$ent.reach -match '(?i)online|up|ok')
            }
        } catch { $online = $false }
        if (-not $online) { continue }
        $count = $null
        if ($entNames -contains 'workers' -and ($ent.workers -is [System.Collections.IList] -or ($ent.workers -is [System.Array]))) {
            try { $count = @($ent.workers).Count } catch { $count = $null }
        }
        if ($null -eq $count -and $entNames -contains 'worker_lines') {
            try { $count = @($ent.worker_lines | Where-Object { $_ }).Count } catch { $count = $null }
        }
        if ($null -eq $count) { $count = Get-BobTrayDigestMachineWorkerCount -Ent $ent }
        if ($null -eq $count -or [int]$count -gt 0) { continue }
        [void]$alerts.Add((
            'ACTION_REQUIRED: online_zero_workers machine={0} offerable={1} start seats via TipForm Agents (FR #9462 / #3180)' -f $mid, $OfferableCount
        ))
    }
    return @($alerts.ToArray())
}

function Format-BobTrayOnlineZeroCaption {
    <#
    FR #9462: TipForm / Status caption naming empty online machines while work is offerable.
    #>
    param(
        $Machines,
        [int]$OfferableCount = 0
    )
    $alerts = @(Get-BobTrayOnlineZeroWorkerAlerts -Machines $Machines -OfferableCount $OfferableCount)
    if ($alerts.Count -lt 1) { return $null }
    $ids = New-Object System.Collections.Generic.List[string]
    foreach ($a in $alerts) {
        if ($a -match 'machine=([^\s]+)') { [void]$ids.Add($Matches[1]) }
    }
    if ($ids.Count -lt 1) { return $null }
    return ('online_zero_workers={0} offerable={1} - TipForm Agents (no auto-start)' -f (($ids | Select-Object -Unique) -join ','), $OfferableCount)
}

function Get-BobTrayEngineStormAlert {
    <#
    FR #9471: TipForm alert while HealEngine storm stamp run/startworker/engine.storm is fresh.
    Operator: TipForm Reload engine / restart tray so !startworker can ACK again.
    #>
    param(
        [string]$Root = '',
        [double]$MaxAgeSeconds = 600
    )
    try {
        if (-not $Root) { return $null }
        $storm = Join-Path (Join-Path (Join-Path $Root 'run') 'startworker') 'engine.storm'
        if (-not (Test-Path -LiteralPath $storm)) { return $null }
        $age = ([datetime]::UtcNow - (Get-Item -LiteralPath $storm).LastWriteTimeUtc).TotalSeconds
        if ($age -lt 0) { $age = 0 }
        if ($age -gt $MaxAgeSeconds) { return $null }
        return ('engine_restart_storm age={0:0}s - TipForm Reload engine (FR #9471)' -f $age)
    } catch { return $null }
}

function Get-BobTrayAgentSeatUnionCount {
    <#
    MRB #8445 / FR #3181 / FR #4458: same agent-seat union CapRefusal uses
    (process roots + uncovered IRC markers). Empty-online fill must not treat
    a marker-only live seat as zero agents.
    #>
    param(
        [object[]]$Procs = $null
    )
    if ($null -eq $Procs) {
        $Procs = @(Get-CimInstance Win32_Process -Filter "Name like 'bob-worker%'" -ErrorAction SilentlyContinue |
                Select-Object ProcessId, ParentProcessId, Name, CommandLine)
    }
    $markers = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($p in @(Get-BobTrayIrcAgentSeatPids)) {
        if ($null -eq $p -or $p -eq '') { continue }
        if ($p -is [System.Collections.Generic.HashSet[int]]) {
            foreach ($x in $p) { [void]$markers.Add([int]$x) }
        } else {
            [void]$markers.Add([int]$p)
        }
    }
    $w = @($Procs | Where-Object { $_.Name -match '^bob-worker(-[0-9a-f]+)?\.exe$' })
    $parentOf = @{}
    foreach ($proc in $w) { $parentOf[[int]$proc.ProcessId] = [int]$proc.ParentProcessId }
    $ids = @($w | ForEach-Object { [int]$_.ProcessId })
    $roots = @($w | Where-Object { $ids -notcontains [int]$_.ParentProcessId })
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($r in $roots) {
        if ((Get-BobTrayWorkerSeatMode $r) -eq 'agent') {
            [void]$pids.Add([int]$r.ProcessId)
        }
    }
    foreach ($m in $markers) {
        $cur = [int]$m
        $seen = @{}
        $covered = $false
        while ($cur -gt 0 -and -not $seen.ContainsKey([string]$cur)) {
            $seen[[string]$cur] = $true
            if ($pids.Contains($cur)) { $covered = $true; break }
            if (-not $parentOf.ContainsKey($cur)) { break }
            $cur = [int]$parentOf[$cur]
        }
        if (-not $covered) { [void]$pids.Add([int]$m) }
    }
    return [int]$pids.Count
}

function Write-BobTrayAlive {
    <#
    .SYNOPSIS
      Heartbeat stamp for run\startworker\tray.alive (FR #2697).
    .NOTES
      FR #5145 / #5346: bob-tray.exe and the PS trayAliveTimer both write this file every ~2s.
      Bare Set-Content / File.WriteAllText take exclusive locks and throw
      "being used by another process", which FR #5050 then intakes as a crash.
      Use OpenOrCreate + FileShare.ReadWrite|Delete + short retries. Sharing miss is not a crash.
    #>
    param(
        [Parameter(Mandatory)][string]$Dir,
        [int]$Retries = 12,
        [int]$DelayMs = 40
    )
    try {
        # FR #5346: OpenOrCreate + share miss is not a crash.
        if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Force -Path $Dir | Out-Null }
        $f = Join-Path $Dir 'tray.alive'
        $payload = '{0} pid={1}' -f [datetime]::UtcNow.ToString('o'), $PID
        $bytes = [Text.Encoding]::ASCII.GetBytes($payload)
        for ($i = 0; $i -lt $Retries; $i++) {
            try {
                $fs = [IO.File]::Open(
                    $f,
                    [IO.FileMode]::OpenOrCreate,
                    [IO.FileAccess]::Write,
                    [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
                )
                try {
                    $fs.SetLength(0)
                    $fs.Write($bytes, 0, $bytes.Length)
                    $fs.Flush()
                }
                finally { $fs.Dispose() }
                return $true
            }
            catch {
                if ($i -ge ($Retries - 1)) { return $false }
                Start-Sleep -Milliseconds ($DelayMs * ($i + 1))
            }
        }
        return $false
    }
    catch { return $false }
}

function Write-BobTraySeatStart {
    <#
    FR #7652: one tray-engine log line for every seat start. Timestamp is added by Write-TrayLog.
    Seat id and trigger are restricted to a safe token so the line cannot carry a secret.
    #>
    param(
        [Parameter(Mandatory)][scriptblock]$Log,
        [string]$SeatId = 'unknown',
        [int]$WorkerPid = 0,
        [Parameter(Mandatory)][string]$Trigger
    )
    $seat = [string]$SeatId
    if ($seat -match '(?i)token|password|secret|bearer') { $seat = 'redacted' }
    $seat = ($seat -replace '[^A-Za-z0-9._-]', '')
    if (-not $seat) { $seat = 'unknown' }
    $trig = ([string]$Trigger -replace '[^A-Za-z0-9._-]', '')
    if (-not $trig) { $trig = 'other' }
    & $Log ('seat-start seat={0} pid={1} trigger={2}' -f $seat, $WorkerPid, $trig)
}

function ConvertTo-BobTrayStartWorkerExpires {
    <#
    FR #8517: ear/startworker.py writes unix-int ts/expires. Hand-rolled or WinRM
    req files sometimes use ISO-8601; a bare [int64] cast threw and skipped res-*.json.
    Accept unix seconds (int/long/numeric string) or ISO-8601; else return $null.
    #>
    param([Parameter(Mandatory)]$Raw)
    if ($null -eq $Raw) { return $null }
    try {
        if ($Raw -is [datetime]) { return ([datetime]$Raw).ToUniversalTime() }
        $s = [string]$Raw
        if (-not $s) { return $null }
        $asLong = 0L
        if ([int64]::TryParse($s, [ref]$asLong)) {
            return [DateTimeOffset]::FromUnixTimeSeconds($asLong).UtcDateTime
        }
        $dto = [DateTimeOffset]::Parse($s, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
        return $dto.UtcDateTime
    }
    catch { return $null }
}


function Resolve-BobTrayOpencodeSlotModel {
  <#
  FR #8610 / #6429: resolve free|paid OpenCode model id for !startworker slot pins.
  #>
  param([string]$Root, [Parameter(Mandatory)][string]$Slot)
  $slot = ([string]$Slot).Trim().ToLowerInvariant()
  $freeDef = 'opencode/deepseek-v4.1-flash-free'
  # FR #6429 / tray default.json models.opencodePaid (never invent a free-pool leaf).
  $paidDef = 'opencode-go/deepseek-v4-pro'
  $free = $freeDef
  $paid = $paidDef
  if (Get-Command Get-BobTrayClickModelConfigPaths -ErrorAction SilentlyContinue) {
    foreach ($path in @(Get-BobTrayClickModelConfigPaths -Root $Root)) {
      if (-not (Test-Path -LiteralPath $path)) { continue }
      try {
        $doc = Get-Content -LiteralPath $path -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($doc.models) {
          if ($doc.models.opencodeFree) { $free = ([string]$doc.models.opencodeFree).Trim() }
          if ($doc.models.opencodePaid) { $paid = ([string]$doc.models.opencodePaid).Trim() }
        }
      } catch { }
    }
  }
  if ($slot -eq 'paid') {
    if ($paid -and $paid -notmatch '\$') { return $paid }
    return $paidDef
  }
  if ($free -and $free -notmatch '\$') { return $free }
  return $freeDef
}

function Get-BobTrayLaunchPidFromOutput {
    <#
    .SYNOPSIS
      FR #8864: last numeric pid in a Launch scriptblock output. Log strings are ignored.
      A later explicit 0 (cap / missing exe) still wins over an earlier pid.
    #>
    param($Output)
    $found = 0
    $saw = $false
    foreach ($item in @($Output)) {
        if ($null -eq $item) { continue }
        $n = $null
        if (($item -is [int]) -or ($item -is [long]) -or ($item -is [double]) -or ($item -is [decimal])) {
            $n = [int]$item
        } elseif ($item -is [string]) {
            $text = $item.Trim()
            if ($text -match '^\d+$') { $n = [int]$text }
        } else {
            try {
                if ($item.PSObject.Properties['Id']) { $n = [int]$item.Id }
                elseif ($item.PSObject.Properties['ProcessId']) { $n = [int]$item.ProcessId }
            } catch { $n = $null }
        }
        if ($null -ne $n) { $found = $n; $saw = $true }
    }
    if (-not $saw -or $found -lt 0) { return 0 }
    return $found
}

function Invoke-BobTrayStartWorkerQueue {
    <#
    .SYNOPSIS
      One tick: heartbeat, then consume every req-*.json. -Launch is
      { param($mode, $agent, $model, $trigger) ... return pid } (Start-BobTrayWorkerExe in the tray).
      FR #9240: kind=auto / empty-* / undercap-* use trigger auto-start and are refused when
      empty-online.disabled is present (reason empty-online-disabled + dedupe intake).
      Explicit !startworker (no kind=auto) uses trigger startworker and still launches.
    .OUTPUTS
      One object per request: id, ok, reason, mode, pid.
    #>
    param(
        [Parameter(Mandatory)][string]$Dir,
        [Parameter(Mandatory)][scriptblock]$Launch,
        [scriptblock]$Log = { param($m) },
        [datetime]$Now = [datetime]::UtcNow,
        [string]$Root = ''
    )
    [void](Write-BobTrayAlive -Dir $Dir)
    $gateRoot = $Root
    if (-not $gateRoot) { $gateRoot = [string]$script:RepoRoot }
    $reqs = @(Get-ChildItem -LiteralPath $Dir -Filter 'req-*.json' -File -ErrorAction SilentlyContinue | Sort-Object Name)
    foreach ($f in $reqs) {
        $req = $null
        try { $req = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
        # delete FIRST: at-most-once, a crashing launch can never be replayed
        try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop } catch { continue }
        $id = [string]$f.BaseName.Substring(4)
        $mode = ''
        $reason = ''
        $pidOut = 0
        $ok = $false
        if (-not $req) { $reason = 'unreadable' }
        else {
            $mode = [string]$req.mode
            $agent = ''
            if ($req.PSObject.Properties.Name -contains 'agent') { $agent = ([string]$req.agent).Trim().ToLowerInvariant() }
            # FR #8610: optional free|paid OpenCode slot -> child-only BOB_OPENCODE_MODEL.
            $slot = ''
            if ($req.PSObject.Properties.Name -contains 'slot') { $slot = ([string]$req.slot).Trim().ToLowerInvariant() }
            $model = ''
            $resolveRoot = $gateRoot
            if (-not $resolveRoot) { $resolveRoot = [string]$script:RepoRoot }
            if ($agent -eq 'opencode' -and $slot -in @('free', 'paid')) {
                if (Get-Command Resolve-BobTrayOpencodeSlotModel -ErrorAction SilentlyContinue) {
                    $model = [string](Resolve-BobTrayOpencodeSlotModel -Root $resolveRoot -Slot $slot)
                }
                elseif ((Get-Command Get-BobTrayClickedLaunchModel -ErrorAction SilentlyContinue) -and $slot -eq 'free') {
                    $model = [string](Get-BobTrayClickedLaunchModel -Root $resolveRoot -Kind 'opencode')
                }
            }
            # FR #9240: auto fill reqs vs explicit !startworker.
            $kind = ''
            if ($req.PSObject.Properties.Name -contains 'kind') { $kind = ([string]$req.kind).Trim().ToLowerInvariant() }
            $launchTrigger = 'startworker'
            if ($kind -eq 'auto' -or $id -match '^(empty-|undercap-)') {
                $launchTrigger = 'auto-start'
            }
            # FR #8517: never throw on expires; always leave a res-*.json reason.
            $expires = ConvertTo-BobTrayStartWorkerExpires -Raw $req.expires
            if ($null -eq $expires) { $reason = 'bad-expires' }
            elseif ($mode -notin @('agent', 'plan')) { $reason = 'bad-mode' }
            elseif ($agent -and $agent -notin @('auto', 'grok', 'cursor', 'opencode')) { $reason = 'bad-agent' }
            elseif ($slot -and $slot -notin @('free', 'paid')) { $reason = 'bad-slot' }
            elseif ($slot -and $agent -ne 'opencode') { $reason = 'bad-slot' }
            elseif ($Now -gt $expires) { $reason = 'expired' }
            elseif ($mode -eq 'agent' -and (Test-BobTraySeatsOff)) { $reason = 'seats-off' }
            elseif (
                $mode -eq 'agent' -and $gateRoot -and
                (Get-Command Test-BobTrayEmptyOnlineBlocksAutoStart -ErrorAction SilentlyContinue) -and
                (Test-BobTrayEmptyOnlineBlocksAutoStart -Root $gateRoot -Trigger $launchTrigger)
            ) {
                # FR #9240: kill switch blocks kind=auto / empty-* / undercap-* launches.
                $reason = 'empty-online-disabled'
                try {
                    if (Get-Command Write-BobTrayUnrequestedSeatStartIntake -ErrorAction SilentlyContinue) {
                        [void](Write-BobTrayUnrequestedSeatStartIntake -Root $gateRoot -Trigger $launchTrigger -Site 'Invoke-BobTrayStartWorkerQueue')
                    }
                } catch { }
                try { & $Log ('startworker {0}: refused empty-online.disabled trigger={1}' -f $id, $launchTrigger) } catch { }
            }
            elseif ((Get-BobTrayWorkerCapRefusal -Mode $mode)) { $reason = 'cap' }
            else {
                try {
                    if ($agent -and $agent -ne 'auto') {
                        $pidOut = [int](Get-BobTrayLaunchPidFromOutput -Output @(& $Launch $mode $agent $model $launchTrigger))
                    }
                    else {
                        $pidOut = [int](Get-BobTrayLaunchPidFromOutput -Output @(& $Launch $mode '' '' $launchTrigger))
                    }
                    if ($pidOut -gt 0) { $ok = $true } else { $reason = 'launch-failed' }
                }
                catch { $reason = 'launch-error: ' + $_.Exception.Message }
            }
        }
        try {
            & $Log ('startworker {0}: ok={1} mode={2} pid={3} reason={4} by={5}' -f $id, $ok, $mode, $pidOut, $reason, $(if ($req) { [string]$req.by } else { '-' }))
        }
        catch { }
        try {
            $res = [ordered]@{ id = $id; ok = $ok; reason = $reason; mode = $mode; pid = $pidOut }
            Set-Content -LiteralPath (Join-Path $Dir ('res-{0}.json' -f $id)) -Value ($res | ConvertTo-Json -Compress) -Encoding ASCII
            # keep the audit trail short
            Get-ChildItem -LiteralPath $Dir -Filter 'res-*.json' -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
                ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force } catch { } }
        }
        catch { }
        [pscustomobject]@{ id = $id; ok = $ok; reason = $reason; mode = $mode; pid = $pidOut }
    }
}

# t815u / FR #2522 / FR #2667: hard cap of 2 AGENT seats per machine (plan/monitor/maintenance are uncapped
# and do not count). Count LIVE bob-worker*.exe seat roots whose CommandLine --mode is agent (default).
# FR #2556: reclaim by seat root trees only (see Stop-BobWorkerSeatTrees); never flat Skip-N.
# (a onefile exe = bootloader + same-named child = one seat; stale run dirs never count). Shared by the tray click and !startworker.
# FR #2523: Watch-AgentHealth / legacy watch seats are NOT counted here and must not start as shop workers when bob-worker is installed.
$script:BobTrayHardMaxWorkers = 2

function Test-BobWorkerProductActive {
    <#
    FR #2523: True when bob-worker.exe is the active product under InstallRoot (or common ai roots).
    Legacy Watch-AgentHealth must not auto-start / join shop alongside it.
    #>
    param(
        [string]$InstallRoot = ''
    )
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($InstallRoot) {
        $candidates.Add((Join-Path $InstallRoot 'worker\bob-worker.exe'))
    }
    if ($script:RepoRoot) {
        $candidates.Add((Join-Path $script:RepoRoot 'worker\bob-worker.exe'))
    }
    foreach ($root in @('C:\ai\bob', 'D:\ai\bob', 'E:\ai\bob')) {
        if (Test-Path -LiteralPath $root) {
            $candidates.Add((Join-Path $root 'worker\bob-worker.exe'))
        }
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $true }
    }
    return $false
}

function Get-BobTrayWorkerSeatMode {
    <# FR #2667 / FR #3181: parse --mode from CommandLine; missing/unreadable => unknown (never agent). #>
    param($Proc)
    $cl = ''
    try { $cl = [string]$Proc.CommandLine } catch { $cl = '' }
    if (-not $cl) {
        try { $cl = [string]$Proc.mode } catch { $cl = '' }
    }
    if ($cl -match '(?i)--mode[=\s]+(agent|plan|monitor|maintenance)\b') {
        return $Matches[1].ToLowerInvariant()
    }
    $low = ($cl).Trim().ToLowerInvariant()
    if ($low -in @('agent', 'plan', 'monitor', 'maintenance')) { return $low }
    return 'unknown'
}


function Get-BobTrayIrcSeatsDir {
    $la = $env:LOCALAPPDATA
    if (-not $la) { $la = Join-Path $env:USERPROFILE 'AppData\Local' }
    return (Join-Path $la 'Bobiverse\worker\run\seats')
}

function Measure-BobTrayIrcAgentSeats {
    <# FR #3181: count IRC-joined agent seat markers with live pids. #>
    param([string]$SeatsDir = '')
    if (-not $SeatsDir) { $SeatsDir = Get-BobTrayIrcSeatsDir }
    if (-not (Test-Path -LiteralPath $SeatsDir)) { return 0 }
    $count = 0
    Get-ChildItem -LiteralPath $SeatsDir -Filter '*.irc.json' -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $j = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.mode -and ([string]$j.mode).ToLowerInvariant() -ne 'agent') { return }
            $seatPid = [int]$j.pid
            if ($seatPid -le 0) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue; return }
            if (Get-Process -Id $seatPid -ErrorAction SilentlyContinue) { $count++ }
            else { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        } catch {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    return [int]$count
}

function Get-BobTrayIrcAgentSeatPids {
    <# FR #4307: live IRC agent marker pids (stale files removed). #>
    param([string]$SeatsDir = '')
    if (-not $SeatsDir) { $SeatsDir = Get-BobTrayIrcSeatsDir }
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'
    if (-not (Test-Path -LiteralPath $SeatsDir)) { return $pids }
    Get-ChildItem -LiteralPath $SeatsDir -Filter '*.irc.json' -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $j = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.mode -and ([string]$j.mode).ToLowerInvariant() -ne 'agent') { return }
            $seatPid = [int]$j.pid
            if ($seatPid -le 0) { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue; return }
            if (Get-Process -Id $seatPid -ErrorAction SilentlyContinue) { [void]$pids.Add($seatPid) }
            else { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        } catch {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    # Unary comma: PS must not unroll a 1-element HashSet into a bare [int] (MRB #4311).
    return ,$pids
}

function Measure-BobTrayWorkerSeats {
    <#
    Root bob-worker*.exe seats (never Watch-AgentHealth) - FR #2523 / t815u.
    FR #2667 / #2522: -Modes defaults to agent only (plan/maintenance do not count toward the hard cap).
    #>
    param(
        [object[]]$Procs,
        [string[]]$Modes = @('agent')
    )
    $wanted = @($Modes | ForEach-Object { ([string]$_).ToLowerInvariant() } | Select-Object -Unique)
    $w = @($Procs | Where-Object { $_.Name -match '^bob-worker(-[0-9a-f]+)?\.exe$' })
    $ids = @($w | ForEach-Object { [int]$_.ProcessId })
    $roots = @($w | Where-Object { $ids -notcontains [int]$_.ParentProcessId })
    return @($roots | Where-Object { $wanted -contains (Get-BobTrayWorkerSeatMode $_) }).Count
}

function Get-BobTrayWorkerCapRefusal {
    <#
    '' when another worker may start, else the short refusal text (tray dialog / log).
    FR #2667: -Mode plan|monitor|maintenance never refused; only agent starts are capped.
    Count agent seat roots only (same as startworker.count_workers / bob_worker.worker_cap_refusal).
    -Procs is for tests.
    #>
    param(
        [object[]]$Procs = $null,
        [string]$Mode = 'agent'
    )
    $modeL = ([string]$Mode).Trim().ToLowerInvariant()
    if (-not $modeL) { $modeL = 'agent' }
    if ($modeL -ne 'agent') { return '' }
    $cap = $script:BobTrayHardMaxWorkers
    # FR #3181 / FR #4307 / MRB #4311 / FR #4458: agent roots, plus IRC marker pids that
    # are not the onefile child of one of those roots. Math.Max undercounts when the sets
    # are disjoint (IRC-marked seat with unknown cmdline + another live --mode agent).
    if ($null -eq $Procs) {
        $Procs = @(Get-CimInstance Win32_Process -Filter "Name like 'bob-worker%'" -ErrorAction SilentlyContinue |
                Select-Object ProcessId, ParentProcessId, Name, CommandLine)
    }
    $markers = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($p in @(Get-BobTrayIrcAgentSeatPids)) {
        if ($null -eq $p -or $p -eq '') { continue }
        # If PS unrolled a HashSet, $p is [int]; if not, $p may still be HashSet (nested).
        if ($p -is [System.Collections.Generic.HashSet[int]]) {
            foreach ($x in $p) { [void]$markers.Add([int]$x) }
        } else {
            [void]$markers.Add([int]$p)
        }
    }
    $w = @($Procs | Where-Object { $_.Name -match '^bob-worker(-[0-9a-f]+)?\.exe$' })
    $parentOf = @{}
    foreach ($proc in $w) { $parentOf[[int]$proc.ProcessId] = [int]$proc.ParentProcessId }
    $ids = @($w | ForEach-Object { [int]$_.ProcessId })
    $roots = @($w | Where-Object { $ids -notcontains [int]$_.ParentProcessId })
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($r in $roots) {
        if ((Get-BobTrayWorkerSeatMode $r) -eq 'agent') {
            [void]$pids.Add([int]$r.ProcessId)
        }
    }
    foreach ($m in $markers) {
        $cur = [int]$m
        $seen = @{}
        $covered = $false
        while ($cur -gt 0 -and -not $seen.ContainsKey([string]$cur)) {
            $seen[[string]$cur] = $true
            if ($pids.Contains($cur)) { $covered = $true; break }
            if (-not $parentOf.ContainsKey($cur)) { break }
            $cur = [int]$parentOf[$cur]
        }
        if (-not $covered) { [void]$pids.Add([int]$m) }
    }
    $n = [int]$pids.Count
    if ($n -ge $cap) { return ('Max {0} workers ({1} agent seats). Close a worker window first.' -f $cap, $n) }
    return ''
}

# FR #2556: when reclaiming over HARD_MAX_WORKERS, kill SEAT ROOT trees only.
# Never: Get-CimInstance ... | Sort ProcessId | Select -Skip N | Stop-Process
# (onefile = bootloader+child same name; Skip-N by flat PID kills whole seats).
# FR #8597: taskkill /T so OpenCode grandchildren under the seat die with the root
# (one-level ParentProcessId match left hung opencode PIDs alive after !recycle).
function Stop-BobWorkerSeatTrees {
  param([int[]]$RootPids)
  foreach ($root in $RootPids) {
    if ($null -eq $root -or [int]$root -le 0) { continue }
    & taskkill.exe /F /T /PID ([int]$root) 2>$null | Out-Null
  }
}
