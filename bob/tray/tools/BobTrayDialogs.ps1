#Requires -Version 5.1
# t828u: the Acknowledge (About) and Status dialogs are compiled exes (tools\bob-about.exe, tools\bob-status.exe; sources in
# dialogs\). Status shows Grok accounts and the Copilot pool (no Cursor pool bars). The tray only (a) writes the status snapshot
# <root>\run\tray-status.json after every poll and (b) starts the exe.
# Start-Process never waits, so the tray UI thread never blocks on a dialog or on the install scan; each exe is single-instance
# (a second start just brings the open window forward). If an exe is missing the caller falls back to the old in-process dialog.
# ASCII-only for Windows PowerShell 5.1.

function Get-BobTrayDialogExe {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][ValidateSet('about', 'status')][string]$Name)
    $p = Join-Path $Root ('tools\bob-{0}.exe' -f $Name)
    if (Test-Path -LiteralPath $p -PathType Leaf) { return $p }
    return $null
}

function Test-BobTrayClickFixParkPresent {
    <#
    FR #9165: while bob-tray.exe is clickfix-parked, TipForm Watch owns the icon —
    skip bob-status.exe and paint the in-process tip card instead.
    #>
    param([Parameter(Mandatory)][string]$Root)
    $tools = Join-Path $Root 'tools'
    foreach ($leaf in @(
            'bob-tray.exe.clickfalse-park',
            'bob-tray.exe.clicktrue-park',
            'bob-tray.exe.clickfix-park'
        )) {
        if (Test-Path -LiteralPath (Join-Path $tools $leaf) -PathType Leaf) { return $true }
    }
    return $false
}

function Test-BobTrayStatusWindowVisible {
    # FR #9165: any bob-status with a non-zero MainWindowHandle counts as painted.
    foreach ($pr in @(Get-Process -Name 'bob-status' -ErrorAction SilentlyContinue)) {
        try {
            if ($pr.MainWindowHandle -ne [IntPtr]::Zero) { return $true }
        } catch { }
    }
    return $false
}

function Stop-BobTrayWindowlessStatus {
    # FR #9165: kill windowless bob-status so the single-instance mutex can clear.
    $n = 0
    foreach ($pr in @(Get-Process -Name 'bob-status' -ErrorAction SilentlyContinue)) {
        try {
            if ($pr.MainWindowHandle -eq [IntPtr]::Zero) {
                Stop-Process -Id $pr.Id -Force -ErrorAction SilentlyContinue
                $n++
            }
        } catch { }
    }
    return $n
}

function Start-BobTrayDialog {
    # Returns $true when the exe was started and (for status) a visible HWND exists.
    # FR #9165: windowless single-instance must not look like success — TipForm falls back.
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][ValidateSet('about', 'status')][string]$Name)
    $exe = Get-BobTrayDialogExe -Root $Root -Name $Name
    if (-not $exe) { return $false }
    try {
        # FR #2590 / #2585: do not embed quotes in Start-Process ArgumentList values (they become part of --root).
        [void](Start-Process -FilePath $exe -ArgumentList @('--root', $Root) -WorkingDirectory $Root -ErrorAction Stop)
    }
    catch { return $false }
    if ($Name -ne 'status') { return $true }
    # Already painted (second launch brought window forward) or new process got an HWND.
    $deadline = [datetime]::UtcNow.AddMilliseconds(2000)
    while ([datetime]::UtcNow -lt $deadline) {
        if (Test-BobTrayStatusWindowVisible) { return $true }
        Start-Sleep -Milliseconds 100
    }
    $killed = Stop-BobTrayWindowlessStatus
    if ($killed -gt 0) {
        $msg = ("FR #9165 stopped windowless bob-status count={0}" -f $killed)
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) { Write-TrayLog $msg }
        else { Write-Host ("WARN " + $msg) }
    }
    return $false
}

function ConvertTo-BobTrayStatusBar {
    param($RemainingPct)
    $o = [ordered]@{ known = $false; pct = 0; r = 88; g = 166; b = 255 }
    try {
        if (Get-Command Get-BobTrayBarPaint -ErrorAction SilentlyContinue) {
            $p = Get-BobTrayBarPaint -RemainingPct $RemainingPct -BarWidth 100
            if ($p -and $p.known) {
                $o.known = $true; $o.pct = [int]$p.remaining_pct
                if ($null -ne $p.fill_r) { $o.r = [int]$p.fill_r; $o.g = [int]$p.fill_g; $o.b = [int]$p.fill_b }
            }
            return $o
        }
    }
    catch { }
    if ($null -ne $RemainingPct -and [string]$RemainingPct -ne '') { $o.known = $true; $o.pct = [Math]::Max(0, [Math]::Min(100, [int]$RemainingPct)) }
    return $o
}

function New-BobTrayStatusModel {
    <#
      The pure data behind the Status card: Copilot pool + Grok account rows (one per canonical machine with workers as
      "{irc nick}: {doing|idle}"), then alert + version footer. Cursor spending-group bars are omitted after account
      unification (one grok/cursor account per machine). $Hover is Get-BobTrayHover's object.
    #>
    param($Hover, [string]$AlertKind = 'none', [string[]]$Alerts = @(), [string]$Version = '', [string]$Machine = '', [string]$Title = '',
        [string]$Short = '', [bool]$Attention = $false, [int64]$AttentionSeq = 0, [bool]$Pulse = $false)
    $pound = [string][char]0x00A3
    $h = $Hover
    $over = ''
    if ($h -and $null -ne $h.account_overage_gbp -and [string]$h.account_overage_gbp -ne '') {
        $v = 0.0
        if ([double]::TryParse([string]$h.account_overage_gbp, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$v) -and $v -gt 0) {
            $over = ('overspend {0}{1}' -f $pound, $v.ToString('N2', [Globalization.CultureInfo]::InvariantCulture))
        }
    }
    # FR #4938: cursor[] stays empty (obsolete spending-group bars).
    # FR #7243: digest_pools carries every digest fuel family for Status / TipForm.
    $cursor = New-Object System.Collections.Generic.List[object]
    $grok = New-Object System.Collections.Generic.List[object]
    $shown = @{}
    if ($h) {
        foreach ($m in @($h.machines)) {
            if (-not $m) { continue }
            $id = [string]$m.id
            $resolved = $id
            try { if (Get-Command Get-BobCanonicalMachineId -ErrorAction SilentlyContinue) { $resolved = Get-BobCanonicalMachineId $id } } catch { $resolved = $id }
            if (-not $resolved) { continue }
            if ($shown.ContainsKey([string]$resolved)) { continue }   # one row per CANONICAL machine (#79)
            $shown[[string]$resolved] = $true
            $up = ([string]$resolved).ToUpperInvariant()
            $pct = $m.remaining_pct
            # FR #6285: prefer digest xai_weekly pool_heading; bar uses bar_pct (null when stale/no reading).
            $heading = $null
            try { if ($m.pool_heading) { $heading = [string]$m.pool_heading } } catch { }
            if (-not $heading) {
                $pctLabel = $null
                if ($null -ne $pct -and [string]$pct -ne '') { $pctLabel = ('{0}%' -f [int]$pct) }   # 0% is real (#179)
                $seat = [string]$m.seat_label; if (-not $seat) { $seat = [string]$m.seat_email }
                $heading = $up
                if ($seat) { $heading = ('{0}  -  {1}' -f $up, $seat) }
                if ($pctLabel) { $heading = ('{0} ({1})' -f $heading, $pctLabel) }
                if ($pctLabel -and $m.reset_label) { $heading = ('{0} - {1}' -f $heading, [string]$m.reset_label) }
            }
            $barPct = $pct
            try {
                if ($null -ne $m.PSObject.Properties['bar_pct']) { $barPct = $m.bar_pct }
                elseif ($m.fuel_stale) { $barPct = $null }
            } catch { }
            $row = ConvertTo-BobTrayStatusBar -RemainingPct $barPct
            $row.heading = $heading; $row.red = $false; $row.help = ''
            $row.workers = @($m.worker_lines | Where-Object { $_ } | ForEach-Object { [string]$_ })   # "{irc nick}: {doing|idle}" from the digest
            $grok.Add($row)
        }
    }
    $ttl = $Title; if (-not $ttl -and $h) { $ttl = [string]$h.title }
    $copilotPool = $null; $copilotLine = ''; $copilotStaleLine = ''; $copilotFreshUntil = [int64]0
    if ($h) {
        $copilotPool = $h.copilot_pool
        $copilotLine = [string]$h.copilot_line
        try { $copilotStaleLine = [string]$h.copilot_stale_line } catch { }
        try { if ($null -ne $h.copilot_fresh_until) { $copilotFreshUntil = [int64]$h.copilot_fresh_until } } catch { }
    }
    if (-not $copilotLine -and (Get-Command Format-BobCopilotPoolLine -ErrorAction SilentlyContinue)) {
        $copilotLine = Format-BobCopilotPoolLine -Pool $copilotPool
        if (-not $copilotStaleLine) { $copilotStaleLine = Format-BobCopilotPoolLine -Pool $copilotPool -ForceStale }
        if ((Get-Command Get-BobCopilotFreshness -ErrorAction SilentlyContinue)) {
            try {
                $fr = Get-BobCopilotFreshness -Pool $copilotPool
                if ($fr -and $null -ne $fr.fresh_until) { $copilotFreshUntil = [int64]$fr.fresh_until }
            } catch { }
        }
    }
    if (-not $copilotLine) { $copilotLine = 'Copilot - unknown' }
    if (-not $copilotStaleLine) { $copilotStaleLine = 'Copilot - [stale] unknown' }
    # FR #6317: remaining-% bar object for Status UsageRow.
    $copilotBar = $null
    if ($h) {
        try { if ($h.copilot_bar) { $copilotBar = $h.copilot_bar } } catch { }
    }
    if (-not $copilotBar -and (Get-Command Get-BobCopilotMeterBarPct -ErrorAction SilentlyContinue)) {
        $pct = $null
        try { $pct = Get-BobCopilotMeterBarPct -Pool $copilotPool } catch { $pct = $null }
        if ($null -ne $pct) {
            $rgb = $null
            try { if (Get-Command Get-BobTrayBarFillRgb -ErrorAction SilentlyContinue) { $rgb = Get-BobTrayBarFillRgb -Pct ([int]$pct) } } catch { }
            $copilotBar = [pscustomobject]@{
                known = $true
                pct   = [int]$pct
                r     = $(if ($rgb) { [int]$rgb.r } else { 88 })
                g     = $(if ($rgb) { [int]$rgb.g } else { 166 })
                b     = $(if ($rgb) { [int]$rgb.b } else { 255 })
            }
        } else {
            $copilotBar = [pscustomobject]@{ known = $false; pct = 0; r = 88; g = 166; b = 255 }
        }
    }
    if (-not $copilotBar) {
        $copilotBar = [pscustomobject]@{ known = $false; pct = 0; r = 88; g = 166; b = 255 }
    }
    # FR #6147: OpenCode free/go + window lines on Status snapshot (n/a when unknown).
    $opencodeLine = ''
    $opencodeFree = $null
    $opencodeGo = $null
    $opencodeWindows = $null
    $opencodeWindowLines = @()
    $opencodeBars = @()
    if ($h) {
        $opencodeLine = [string]$h.opencode_line
        $opencodeFree = $h.opencode_free
        $opencodeGo = $h.opencode_go
        try { $opencodeWindows = $h.opencode_windows } catch { }
        try { if ($h.opencode_window_lines) { $opencodeWindowLines = @($h.opencode_window_lines) } } catch { }
        try { if ($h.opencode_bars) { $opencodeBars = @($h.opencode_bars) } } catch { }
    }
    if ((@($opencodeWindowLines).Count -eq 0) -and (Get-Command Format-BobOpencodeWindowLines -ErrorAction SilentlyContinue)) {
        $pack = Format-BobOpencodeWindowLines -FreePct $opencodeFree -Windows $opencodeWindows
        if ($pack.summary) { $opencodeLine = [string]$pack.summary }
        $opencodeWindowLines = @()
        if ($pack.free_heading) { $opencodeWindowLines += [string]$pack.free_heading }
        if ($pack.window_lines) { $opencodeWindowLines += @($pack.window_lines) }
        if ($pack.bars) { $opencodeBars = @($pack.bars) }
        if ($pack.windows) { $opencodeWindows = $pack.windows }
        if ($null -eq $opencodeGo -and $null -ne $pack.go_remaining) { $opencodeGo = $pack.go_remaining }
        if ($null -eq $opencodeFree) { $opencodeFree = $pack.free }
    }
    # Exact failed snapshot: hover left free/go/windows null and window_lines empty.
    # FR #7017: Go windows only (never a free row). Unknown stays n/a — never 100%.
    if (@($opencodeWindowLines).Count -eq 0) {
        $opencodeLine = 'OpenCode  go n/a'
        $opencodeWindowLines = @('go rolling  n/a', 'go weekly  n/a', 'go monthly  n/a')
        $opencodeBars = @(
            [pscustomobject]@{ id = 'rolling'; heading = 'go rolling  n/a'; known = $false; pct = 0 },
            [pscustomobject]@{ id = 'week'; heading = 'go weekly  n/a'; known = $false; pct = 0 },
            [pscustomobject]@{ id = 'month'; heading = 'go monthly  n/a'; known = $false; pct = 0 }
        )
        if (-not $opencodeWindows) {
            $opencodeWindows = [pscustomobject]@{
                rolling = [pscustomobject]@{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }
                week    = [pscustomobject]@{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }
                month   = [pscustomobject]@{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }
            }
        }
    }
    if (-not $opencodeLine) { $opencodeLine = 'OpenCode  go n/a' }
    $digestPools = @()
    if ($h) {
        try { if ($h.digest_pools) { $digestPools = @($h.digest_pools) } } catch { }
    }
    if ($digestPools.Count -eq 0 -and (Get-Command Get-BobTrayDigestPoolCatalog -ErrorAction SilentlyContinue)) {
        try { $digestPools = @(Get-BobTrayDigestPoolCatalog -Digest $null) } catch { }
    }
    return [ordered]@{
        v         = 1
        ts        = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        title     = $ttl
        machine   = $Machine
        short     = $Short
        attention = $Attention
        attention_seq = $AttentionSeq
        pulse     = $Pulse
        overspend = $over
        cursor    = @($cursor.ToArray())
        grok      = @($grok.ToArray())
        opencode_free = $opencodeFree
        opencode_go = $opencodeGo
        opencode_line = $opencodeLine
        opencode_windows = $opencodeWindows
        opencode_window_lines = @($opencodeWindowLines)
        opencode_bars = @($opencodeBars)
        copilot_pool = $copilotPool
        copilot_line = $copilotLine
        copilot_stale_line = $copilotStaleLine
        copilot_fresh_until = $copilotFreshUntil
        copilot_bar = $copilotBar
        digest_pools = @($digestPools)
        alert     = $(if ($AlertKind) { $AlertKind } else { 'none' })
        alerts    = @($Alerts | Where-Object { $_ })
        version   = $Version
    }
}

function Update-BobTrayStatusHeartbeat {
    # FR #8971: refresh tray-status.json mtime before a slow digest/hover step.
    param([Parameter(Mandatory)][string]$Root)
    try {
        $path = Join-Path $Root 'run\tray-status.json'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
        $raw = [IO.File]::ReadAllText($path)
        $tmp = $path + '.hb.tmp'
        [IO.File]::WriteAllText($tmp, $raw, (New-Object System.Text.UTF8Encoding $false))
        [IO.File]::Replace($tmp, $path, [NullString]::Value)
        return $path
    }
    catch { return $null }
}

function Write-BobTrayStatusSnapshot {
    # Atomic (temp + replace) so the open card never reads a half-written file. Never throws: the tray poll must not die on this.
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)]$Model)
    try {
        $dir = Join-Path $Root 'run'
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        $path = Join-Path $dir 'tray-status.json'
        $tmp = $path + '.tmp'
        $json = ConvertTo-Json -InputObject $Model -Depth 8 -Compress
        [IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding $false))
        # a bare $null becomes '' in PS5 and Replace then throws 'path is not of a legal form' - pass [NullString]::Value
        if (Test-Path -LiteralPath $path) { [IO.File]::Replace($tmp, $path, [NullString]::Value) } else { [IO.File]::Move($tmp, $path) }
        return $path
    }
    catch { return $null }
}

function Format-BobTrayStatusWorkerLine {
    # Same contract as Format-BobTrayWorkerLine / TipForm (FR #7147 start_model; FR #8155 last_progress).
    param(
        [string]$Nick,
        [string]$State,
        [string]$Work,
        [string]$Kind = '',
        [string]$StartModel = '',
        [bool]$ModelMismatch = $false,
        [string]$StartEffort = '',
        [string]$LastProgress = '',
        [string]$ProgressPhase = ''
    )
    $n = ([string]$Nick).Trim()
    if (-not $n) { return $null }
    $st = ([string]$State).Trim().ToLowerInvariant()
    $text = 'idle'
    if ($st -eq 'doing') {
        $w = ([string]$Work) -replace '[

	]+', ' '
        $w = $w.Trim()
        if (-not $w) { $w = 'working' }
        $text = $w
                # FR #8155: show last_progress age (activity clock), not state-change updated.
        # Get-BobJobAge lives in BobBridge module scope; Dialogs is dot-sourced outside it.
        $lp = ([string]$LastProgress).Trim()
        if ($lp) {
            $age = '?'
            try {
                $t = [datetime]::Parse($lp, $null, [Globalization.DateTimeStyles]::RoundtripKind)
                if ($t.Kind -eq [DateTimeKind]::Unspecified) { $t = [datetime]::SpecifyKind($t, [DateTimeKind]::Utc) }
                $ts = [datetime]::UtcNow - $t.ToUniversalTime()
                if ($ts.TotalHours -ge 1) { $age = ('{0}h{1}m' -f [int]$ts.TotalHours, $ts.Minutes) }
                elseif ($ts.TotalMinutes -ge 1) { $age = ('{0}m' -f [int]$ts.TotalMinutes) }
                elseif ($ts.TotalSeconds -ge 0) { $age = ('{0}s' -f [int]$ts.TotalSeconds) }
            } catch { $age = '?' }
            if ($age -and $age -ne '?') {
                $phase = ([string]$ProgressPhase).Trim()
                if ($phase) { $text = ('{0} · progress {1} ({2})' -f $text, $age, $phase) }
                else { $text = ('{0} · progress {1}' -f $text, $age) }
            }
        }
    }
    elseif ($st -eq 'offered') {
        $w = ([string]$Work) -replace '[

	]+', ' '
        $w = $w.Trim()
        if ($w -and $w -ne 'offered') { $text = ('offered: {0}' -f $w) }
        else { $text = 'offered' }
    }
    $k = ([string]$Kind).Trim()
    $sm = ([string]$StartModel).Trim()
    if ($k -or $sm) {
        $tag = if ($k -and $sm) { '{0}/{1}' -f $k, $sm } elseif ($sm) { $sm } else { $k }
        $eff = ([string]$StartEffort).Trim()
        if ($eff) { $tag = $tag + '/' + $eff }
        if ($ModelMismatch -and $sm) { $tag = $tag + '!' }
        $text = ('[{0}] {1}' -f $tag, $text)
    }
    return ('{0}: {1}' -f $n, $text)
}

function Get-BobTrayLocalSeatWorkerLines {
    <#
      FR #8513: local IRC seat-ledger fallback when remote digest fetch fails or
      returns workers=[] while seats are still alive on this box.
      Reads %LOCALAPPDATA%\Bobiverse\worker\run\seats\*.irc.json (live pid only).
    #>
    param(
        [string]$MachineId = '',
        [string]$SeatsDir = '',
        [switch]$MarkStale
    )
    if (-not $SeatsDir) {
        $la = $env:LOCALAPPDATA
        if (-not $la) { $la = Join-Path $env:USERPROFILE 'AppData\Local' }
        $SeatsDir = Join-Path $la 'Bobiverse\worker\run\seats'
    }
    $lines = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $SeatsDir -PathType Container)) { return @() }
    $wantMid = ([string]$MachineId).Trim().ToLowerInvariant()
    Get-ChildItem -LiteralPath $SeatsDir -Filter '*.irc.json' -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $j = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.mode -and ([string]$j.mode).ToLowerInvariant() -ne 'agent') { return }
            $seatPid = 0
            try { $seatPid = [int]$j.pid } catch { $seatPid = 0 }
            if ($seatPid -le 0) { return }
            if (-not (Get-Process -Id $seatPid -ErrorAction SilentlyContinue)) { return }
            $mid = ([string]$j.machine).Trim().ToLowerInvariant()
            if ($wantMid -and $mid -and $mid -ne $wantMid) { return }
            $nick = ([string]$j.nick).Trim()
            if (-not $nick) { $nick = ('{0}-{1}' -f $(if ($mid) { $mid } else { 'seat' }), $seatPid) }
            $state = 'idle'
            if ($MarkStale) { $state = 'idle' }
            $ln = Format-BobTrayStatusWorkerLine -Nick $nick -State $state -Work $(if ($MarkStale) { 'stale (local)' } else { '' })
            if ($ln) {
                if ($MarkStale -and $ln -notmatch 'stale') {
                    $ln = ('{0} · stale' -f $ln)
                }
                [void]$lines.Add($ln)
            }
        } catch { }
    }
    return @($lines | Sort-Object -Unique)
}

function Get-BobTrayDigestWorkerLinesForMachine {
    # Report-only: machines.<id>.workers as array [{nick,state,work}] or nick-map {nick={state,work|job}}.
    # FR #8513: when workers_stale / digest_post_failed, append a stale marker on each line.
    param($Digest, [string]$MachineId)
    if (-not $Digest -or -not $Digest.machines -or -not $MachineId) { return @() }
    $ent = $null
    foreach ($p in @($Digest.machines.PSObject.Properties)) {
        if ([string]$p.Name -ieq $MachineId) { $ent = $p.Value; break }
    }
    if (-not $ent -or -not ($ent.PSObject.Properties.Name -contains 'workers')) { return @() }
    $node = $ent.workers
    $lines = New-Object System.Collections.Generic.List[string]
    $isNickMap = $false
    if ($node -is [pscustomobject] -or $node -is [System.Collections.IDictionary]) {
        foreach ($prop in @($node.PSObject.Properties)) {
            if ([string]$prop.Name -match '^[A-Za-z0-9_]+-\d+$') { $isNickMap = $true; break }
        }
    }
    if ($isNickMap) {
        foreach ($prop in @($node.PSObject.Properties)) {
            $nick = [string]$prop.Name
            if ($nick -notmatch '^[A-Za-z0-9_]+-\d+$') { continue }
            $val = $prop.Value
            $state = 'idle'; $work = ''; $kind = ''; $sm = ''; $mm = $false; $lp = ''; $pp = ''
            if ($val -is [pscustomobject] -or $val -is [System.Collections.IDictionary]) {
                if ($val.state) { $state = [string]$val.state }
                if ($val.work) { $work = [string]$val.work }
                elseif ($val.job) { $work = [string]$val.job }
                elseif ($val.working_on) { $work = [string]$val.working_on }
                if ($val.kind) { $kind = [string]$val.kind }
                elseif ($val.agent) { $kind = [string]$val.agent }
                if ($val.start_model) { $sm = [string]$val.start_model }
                elseif ($val.model) { $sm = [string]$val.model }
                if ($val.PSObject.Properties.Name -contains 'model_mismatch') { $mm = [bool]$val.model_mismatch }
                if ($val.PSObject.Properties.Name -contains 'last_progress' -and $val.last_progress) {
                    $lp = [string]$val.last_progress
                }
                if ($val.PSObject.Properties.Name -contains 'progress_phase' -and $val.progress_phase) {
                    $pp = [string]$val.progress_phase
                }
            }
            $ln = Format-BobTrayStatusWorkerLine -Nick $nick -State $state -Work $work -Kind $kind -StartModel $sm -ModelMismatch:$mm -LastProgress $lp -ProgressPhase $pp
            if ($ln) { [void]$lines.Add($ln) }
        }
    }
    else {
        foreach ($w in @($node)) {
            if (-not $w) { continue }
            $nick = ''
            $state = 'idle'
            $work = ''
            $kind = ''
            $sm = ''
            $mm = $false
            $lp = ''
            $pp = ''
            if ($w -is [pscustomobject] -or $w -is [System.Collections.IDictionary]) {
                if ($w.nick) { $nick = [string]$w.nick }
                if ($w.state) { $state = [string]$w.state }
                if ($w.work) { $work = [string]$w.work }
                elseif ($w.job) { $work = [string]$w.job }
                if ($w.kind) { $kind = [string]$w.kind }
                elseif ($w.agent) { $kind = [string]$w.agent }
                if ($w.start_model) { $sm = [string]$w.start_model }
                elseif ($w.model) { $sm = [string]$w.model }
                if ($w.PSObject.Properties.Name -contains 'model_mismatch') { $mm = [bool]$w.model_mismatch }
                if ($w.PSObject.Properties.Name -contains 'last_progress' -and $w.last_progress) {
                    $lp = [string]$w.last_progress
                }
                if ($w.PSObject.Properties.Name -contains 'progress_phase' -and $w.progress_phase) {
                    $pp = [string]$w.progress_phase
                }
            }
            $ln = Format-BobTrayStatusWorkerLine -Nick $nick -State $state -Work $work -Kind $kind -StartModel $sm -ModelMismatch:$mm -LastProgress $lp -ProgressPhase $pp
            if ($ln) { [void]$lines.Add($ln) }
        }
    }
    # FR #8513: mark TipForm lines when digest kept last-good / digest_post_failed.
    $stale = $false
    try {
        if ($ent.PSObject.Properties.Name -contains 'workers_stale' -and $ent.workers_stale) { $stale = $true }
        if ($ent.PSObject.Properties.Name -contains 'digest_post_failed' -and $ent.digest_post_failed) { $stale = $true }
    } catch { }
    if ($stale) {
        $marked = New-Object System.Collections.Generic.List[string]
        foreach ($ln in @($lines)) {
            if (-not $ln) { continue }
            if ([string]$ln -match '(?i)\bstale\b') { [void]$marked.Add([string]$ln) }
            else { [void]$marked.Add(('{0} · stale' -f $ln)) }
        }
        return @($marked | Sort-Object)
    }
    return @($lines | Sort-Object)
}

function Sync-BobTrayStatusWorkersFromDigest {
    <#
      FR #1553: refresh TipForm worker lines from the public digest report WITHOUT Get-BobTrayHover.
      Bound HTTP (default 8s) so a peer DNS/UNC hang in hover cannot freeze tray-status.json forever.
      Updates only grok[].workers (+ ts); leaves cursor pools / attention / copilot_* alone (FR #6148).
      -Digest: optional already-parsed digest (tests / callers that fetched elsewhere).
      FR #8513: on digest fetch failure, keep/merge local IRC seat ledger instead of wiping TipForm.
      When digest returns workers=[] for a local machine that still has live seat PIDs, paint local
      nicks marked stale. When digest drops seats and local PIDs are gone, clear those TipForm lines.
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$ReportUrl = '',
        [int]$TimeoutSec = 8,
        $Digest = $null,
        [string]$SeatsDir = ''
    )
    try {
        $path = Join-Path (Join-Path $Root 'run') 'tray-status.json'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
        $digest = $Digest
        $fetchFailed = $false
        if (-not $digest) {
            # FR #6142: trim before blank check (whitespace-only env -> canonical).
            $url = ([string]$ReportUrl).Trim()
            if (-not $url) { $url = ([string]$env:BOB_DIGEST_REPORT_URL).Trim() }
            if (-not $url) { $url = 'https://bob.ntsa.uk/bob/v1/report' }
            $sec = [Math]::Max(2, [int]$TimeoutSec)
            # FR #7615 / #7602: HttpWebRequest Timeout + ReadWriteTimeout (PS 5.1 IWR hang).
            if (-not (Get-Command Invoke-BobDigestHttpGet -ErrorAction SilentlyContinue)) {
                $helperCands = @(
                    (Join-Path $Root 'src\Private\Invoke-BobDigestHttpGet.ps1'),
                    (Join-Path $PSScriptRoot '..\src\Private\Invoke-BobDigestHttpGet.ps1'),
                    (Join-Path (Split-Path $PSScriptRoot -Parent) 'src\Private\Invoke-BobDigestHttpGet.ps1')
                )
                foreach ($hc in $helperCands) {
                    if (Test-Path -LiteralPath $hc -PathType Leaf) { . $hc; break }
                }
            }
            if (-not (Get-Command Invoke-BobDigestHttpGet -ErrorAction SilentlyContinue)) {
                throw 'Invoke-BobDigestHttpGet missing'
            }
            try {
                $got = Invoke-BobDigestHttpGet -Uri $url -TimeoutSec $sec
                if (-not $got -or [int]$got.StatusCode -lt 200 -or [int]$got.StatusCode -ge 300) {
                    throw ('digest HTTP status {0}' -f $(if ($got) { $got.StatusCode } else { 'null' }))
                }
                # UTF-8 body already decoded by Invoke-BobDigestHttpGet (PS 5.1 Latin-1 trap avoided).
                $digest = [string]$got.Text | ConvertFrom-Json
            } catch {
                # FR #8513: fetch failure must not blank TipForm when local seats are alive.
                $fetchFailed = $true
                $digest = $null
            }
        }
        $raw = [IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding $false))
        $model = $raw | ConvertFrom-Json
        if (-not $model) { return $null }
        $grok = @($model.grok)
        if ($grok.Count -eq 0) { return $null }
        if ($fetchFailed -or -not $digest -or -not $digest.machines) {
            $changed = $false
            foreach ($row in $grok) {
                if (-not $row) { continue }
                $heading = [string]$row.heading
                if (-not $heading) { continue }
                $token = ($heading -split '\s+', 2)[0]
                if (-not $token) { continue }
                $mid = $token.Trim().ToLowerInvariant()
                $local = @(Get-BobTrayLocalSeatWorkerLines -MachineId $mid -SeatsDir $SeatsDir -MarkStale)
                if ($local.Count -eq 0) {
                    # No local seats: keep previous TipForm lines but mark them stale.
                    $prev = @($row.workers | ForEach-Object { [string]$_ } | Where-Object { $_ })
                    if ($prev.Count -eq 0) { continue }
                    $marked = @(
                        foreach ($ln in $prev) {
                            if ($ln -match '(?i)\bstale\b') { $ln } else { '{0} · stale' -f $ln }
                        }
                    )
                    $row.workers = @($marked)
                    $changed = $true
                    continue
                }
                $prev = @($row.workers | ForEach-Object { [string]$_ })
                $same = ($prev.Count -eq $local.Count)
                if ($same) {
                    for ($i = 0; $i -lt $prev.Count; $i++) {
                        if ($prev[$i] -cne $local[$i]) { $same = $false; break }
                    }
                }
                if (-not $same) {
                    $row.workers = @($local)
                    $changed = $true
                }
            }
            $model.ts = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            return (Write-BobTrayStatusSnapshot -Root $Root -Model $model)
        }
        $changed = $false
        foreach ($row in $grok) {
            if (-not $row) { continue }
            $heading = [string]$row.heading
            if (-not $heading) { continue }
            $token = ($heading -split '\s+', 2)[0]
            if (-not $token) { continue }
            $mid = $token.Trim().ToLowerInvariant()
            $lines = @(Get-BobTrayDigestWorkerLinesForMachine -Digest $digest -MachineId $mid)
            if ($lines.Count -eq 0) {
                # FR #8513: digest dropped workers — use local live seats (stale) when present;
                # otherwise clear TipForm so idle cards do not outlive the digest.
                $local = @(Get-BobTrayLocalSeatWorkerLines -MachineId $mid -SeatsDir $SeatsDir -MarkStale)
                $lines = @($local)
            }
            $prev = @($row.workers | ForEach-Object { [string]$_ })
            $same = ($prev.Count -eq $lines.Count)
            if ($same) {
                for ($i = 0; $i -lt $prev.Count; $i++) {
                    if ($prev[$i] -cne $lines[$i]) { $same = $false; break }
                }
            }
            if (-not $same) {
                $row.workers = @($lines)
                $changed = $true
            }
        }
        $model.ts = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        if (-not $changed) {
            # Still bump ts so TipForm age stays fresh even when lines unchanged.
            return (Write-BobTrayStatusSnapshot -Root $Root -Model $model)
        }
        return (Write-BobTrayStatusSnapshot -Root $Root -Model $model)
    }
    catch { return $null }
}

# ---- t832u: the compiled tray (tools\bob-tray.exe) owns icon / menu / clicks; this script is then the headless "engine" (BOB_TRAY_ENGINE=1) ----
function Test-BobTrayEngineMode { return ([string]$env:BOB_TRAY_ENGINE -eq '1') }

function Write-BobTrayEngineEnv {
    # The exe starts workers (Agent / Plan click) with the environment the engine got from the seat wrapper.
    param([Parameter(Mandatory)][string]$Root)
    try {
        $dir = Join-Path $Root 'run'
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        $o = [ordered]@{}
        foreach ($e in Get-ChildItem Env: | Where-Object { $_.Name -match '^(BOB_|AGENTIC_|BOBIVERSE_)[A-Z0-9_]+$' -and $_.Name -notmatch 'PASSWORD|SECRET|TOKEN|KEY' }) { $o[$e.Name] = [string]$e.Value }
        $tmp = Join-Path $dir 'tray-env.json.tmp'
        [IO.File]::WriteAllText($tmp, (ConvertTo-Json -InputObject $o -Compress), (New-Object System.Text.UTF8Encoding $false))
        Move-Item -LiteralPath $tmp -Destination (Join-Path $dir 'tray-env.json') -Force
        return $true
    }
    catch { return $false }
}

function Invoke-BobTrayExeCommands {
    <#
      Called every 2 s by the engine. Consumes <root>\run\tray-cmd.txt written by bob-tray.exe: ack | exit | restart.
      FR #5111: leave `reload` lines for the elevated host (KillEngineTree + StartEngine only).
      Also: the engine leaves when its exe parent is gone (BOB_TRAY_EXE_PID) so a crashed/killed tray never leaves an orphan engine.
      -OnAck/-OnExit/-OnRestart/-ParentGone are script blocks (the tray passes its functions; tests pass stubs).
    #>
    param([Parameter(Mandatory)][string]$Root, [scriptblock]$OnAck, [scriptblock]$OnExit, [scriptblock]$OnRestart, [scriptblock]$ParentGone)
    $f = Join-Path (Join-Path $Root 'run') 'tray-cmd.txt'
    $done = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $f) {
        # FR #5177: claim before callbacks; a restart may kill this engine before returning.
        # New commands go to $f and must not be deleted with the claimed batch.
        $claimed = $f + '.' + [guid]::NewGuid().ToString('N') + '.pending'
        try {
            Move-Item -LiteralPath $f -Destination $claimed -ErrorAction Stop
            $lines = @(Get-Content -LiteralPath $claimed -ErrorAction Stop)
            $keep = @($lines | Where-Object { ([string]$_).Trim().ToLowerInvariant() -eq 'reload' })
            if ($keep.Count -gt 0) {
                Add-Content -LiteralPath $f -Value $keep -Encoding ascii -ErrorAction Stop
            }
            Remove-Item -LiteralPath $claimed -Force -ErrorAction Stop
        } catch { return $done.ToArray() }
        foreach ($l in $lines) {
            $cmd = ([string]$l).Trim().ToLowerInvariant()
            if ($cmd -eq 'reload') { continue }
            if ($cmd -eq 'ack' -and $OnAck) { & $OnAck; $done.Add('ack') }
            elseif ($cmd -eq 'exit' -and $OnExit) { & $OnExit; $done.Add('exit'); break }
            elseif ($cmd -eq 'restart' -and $OnRestart) { & $OnRestart; $done.Add('restart'); break }
        }
    }
    $pidText = [string]$env:BOB_TRAY_EXE_PID
    if ($done.Count -eq 0 -and $pidText -match '^\d+$' -and $ParentGone) {
        $alive = $true
        try { $alive = [bool](Get-Process -Id ([int]$pidText) -ErrorAction Stop) } catch { $alive = $false }
        if (-not $alive) { & $ParentGone; $done.Add('parent-gone') }
    }
    return $done.ToArray()
}
