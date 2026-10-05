#Requires -Version 5.1
# t828u: the Acknowledge (About) and Status (pools) dialogs are compiled exes (tools\bob-about.exe, tools\bob-status.exe; sources in
# dialogs\). The tray only (a) writes the status snapshot <root>\run\tray-status.json after every poll and (b) starts the exe.
# Start-Process never waits, so the tray UI thread never blocks on a dialog or on the install scan; each exe is single-instance
# (a second start just brings the open window forward). If an exe is missing the caller falls back to the old in-process dialog.
# ASCII-only for Windows PowerShell 5.1.

function Get-BobTrayDialogExe {
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][ValidateSet('about', 'status')][string]$Name)
    $p = Join-Path $Root ('tools\bob-{0}.exe' -f $Name)
    if (Test-Path -LiteralPath $p -PathType Leaf) { return $p }
    return $null
}

function Start-BobTrayDialog {
    # Returns $true when the exe was started (it may exit at once if its window is already open: single instance).
    param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][ValidateSet('about', 'status')][string]$Name)
    $exe = Get-BobTrayDialogExe -Root $Root -Name $Name
    if (-not $exe) { return $false }
    try {
        # FR #2590 / #2585: do not embed quotes in Start-Process ArgumentList values (they become part of --root).
        [void](Start-Process -FilePath $exe -ArgumentList @('--root', $Root) -WorkingDirectory $Root -ErrorAction Stop)
        return $true
    }
    catch { return $false }
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
      The pure data behind the Status card, in the exact order the old card drew it: Cursor pools first (fleet), then one Grok row per
      canonical machine with its workers as "{irc nick}: {doing|idle}", then alert + version footer. $Hover is Get-BobTrayHover's object.
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
    $isRed = { param($label) ($label -and (([string]$label) -match '^-' -or ([string]$label).IndexOf([char]0x00A3) -ge 0)) }
    $cursor = New-Object System.Collections.Generic.List[object]
    $pools = @(); if ($h) { $pools = @($h.cursor_pools | Where-Object { $_ }) }
    if ($pools.Count -gt 0) {
        foreach ($pool in $pools) {
            $heading = [string]$pool.heading
            if (-not $heading) { continue }
            $help = ''
            try {
                $gid = [string]$pool.group_id
                if (-not $gid -and $pool.id) { $gid = [string]$pool.id }
                if (Get-Command Get-BobTrayCursorGroupHelpTooltip -ErrorAction SilentlyContinue) { $help = [string](Get-BobTrayCursorGroupHelpTooltip -GroupId $gid) }
            }
            catch { }
            $row = ConvertTo-BobTrayStatusBar -RemainingPct $pool.remaining_pct
            $row.heading = $heading; $row.red = [bool](& $isRed ([string]$pool.pct_label)); $row.help = $help
            $cursor.Add($row)
        }
    }
    elseif ($h) {
        $acctName = 'cursor'; if ($h.account_name) { $acctName = [string]$h.account_name }
        $acctLabel = [string]$h.account_label
        if (-not $acctLabel) {
            try { $acctLabel = [string](Format-BobCursorAccountLabel -RemainingPct $h.account_remaining_pct -UsedPct $null) } catch { $acctLabel = 'empty' }
        }
        $heading = ('{0} ({1})' -f $acctName, $acctLabel)
        if ($h.account_reset_label) { $heading = ('{0} - {1}' -f $heading, [string]$h.account_reset_label) }
        $row = ConvertTo-BobTrayStatusBar -RemainingPct $h.account_remaining_pct
        $row.heading = $heading; $row.red = [bool](& $isRed $acctLabel); $row.help = ''
        $cursor.Add($row)
    }
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
            $pctLabel = $null
            if ($null -ne $pct -and [string]$pct -ne '') { $pctLabel = ('{0}%' -f [int]$pct) }   # 0% is real (#179)
            $seat = [string]$m.seat_label; if (-not $seat) { $seat = [string]$m.seat_email }
            $heading = $up
            if ($seat) { $heading = ('{0}  -  {1}' -f $up, $seat) }
            if ($pctLabel) { $heading = ('{0} ({1})' -f $heading, $pctLabel) }
            if ($pctLabel -and $m.reset_label) { $heading = ('{0} - {1}' -f $heading, [string]$m.reset_label) }
            $row = ConvertTo-BobTrayStatusBar -RemainingPct $pct
            $row.heading = $heading; $row.red = $false; $row.help = ''
            $row.workers = @($m.worker_lines | Where-Object { $_ } | ForEach-Object { [string]$_ })   # "{irc nick}: {doing|idle}" from the digest
            $grok.Add($row)
        }
    }
    $ttl = $Title; if (-not $ttl -and $h) { $ttl = [string]$h.title }
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
        alert     = $(if ($AlertKind) { $AlertKind } else { 'none' })
        alerts    = @($Alerts | Where-Object { $_ })
        version   = $Version
    }
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
    # Same contract as Format-BobTrayWorkerLine / TipForm: "{irc nick}: {doing|offered|idle}".
    param([string]$Nick, [string]$State, [string]$Work)
    $n = ([string]$Nick).Trim()
    if (-not $n) { return $null }
    $st = ([string]$State).Trim().ToLowerInvariant()
    $text = 'idle'
    if ($st -eq 'doing') {
        $w = ([string]$Work) -replace '[\r\n\t]+', ' '
        $w = $w.Trim()
        if (-not $w) { $w = 'working' }
        $text = $w
    }
    elseif ($st -eq 'offered') {
        $w = ([string]$Work) -replace '[\r\n\t]+', ' '
        $w = $w.Trim()
        if ($w -and $w -ne 'offered') { $text = ('offered: {0}' -f $w) }
        else { $text = 'offered' }
    }
    return ('{0}: {1}' -f $n, $text)
}

function Get-BobTrayDigestWorkerLinesForMachine {
    # Report-only: machines.<id>.workers as array [{nick,state,work}] or nick-map {nick={state,work|job}}.
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
            $state = 'idle'; $work = ''
            if ($val -is [pscustomobject] -or $val -is [System.Collections.IDictionary]) {
                if ($val.state) { $state = [string]$val.state }
                if ($val.work) { $work = [string]$val.work }
                elseif ($val.job) { $work = [string]$val.job }
                elseif ($val.working_on) { $work = [string]$val.working_on }
            }
            $ln = Format-BobTrayStatusWorkerLine -Nick $nick -State $state -Work $work
            if ($ln) { [void]$lines.Add($ln) }
        }
    }
    else {
        foreach ($w in @($node)) {
            if (-not $w) { continue }
            $nick = ''
            $state = 'idle'
            $work = ''
            if ($w -is [pscustomobject] -or $w -is [System.Collections.IDictionary]) {
                if ($w.nick) { $nick = [string]$w.nick }
                if ($w.state) { $state = [string]$w.state }
                if ($w.work) { $work = [string]$w.work }
                elseif ($w.job) { $work = [string]$w.job }
            }
            $ln = Format-BobTrayStatusWorkerLine -Nick $nick -State $state -Work $work
            if ($ln) { [void]$lines.Add($ln) }
        }
    }
    return @($lines | Sort-Object)
}

function Sync-BobTrayStatusWorkersFromDigest {
    <#
      FR #1553: refresh TipForm worker lines from the public digest report WITHOUT Get-BobTrayHover.
      Bound HTTP (default 8s) so a peer DNS/UNC hang in hover cannot freeze tray-status.json forever.
      Updates only grok[].workers (+ ts); leaves cursor pools / attention alone.
      -Digest: optional already-parsed digest (tests / callers that fetched elsewhere).
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$ReportUrl = '',
        [int]$TimeoutSec = 8,
        $Digest = $null
    )
    try {
        $path = Join-Path (Join-Path $Root 'run') 'tray-status.json'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
        $digest = $Digest
        if (-not $digest) {
            $url = [string]$ReportUrl
            if (-not $url) { $url = [string]$env:BOB_DIGEST_REPORT_URL }
            if (-not $url) { $url = 'https://irc.ntsa.uk/bob/v1/report' }
            $url = $url.Trim()
            $sec = [Math]::Max(2, [int]$TimeoutSec)
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $sec -Headers @{ Accept = 'application/json' }
            $ms = $resp.RawContentStream
            $ms.Position = 0
            $buf = New-Object byte[] ([int]$ms.Length)
            [void]$ms.Read($buf, 0, $buf.Length)
            $digest = [System.Text.Encoding]::UTF8.GetString($buf) | ConvertFrom-Json
        }
        if (-not $digest -or -not $digest.machines) { return $null }
        $raw = [IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding $false))
        $model = $raw | ConvertFrom-Json
        if (-not $model) { return $null }
        $grok = @($model.grok)
        if ($grok.Count -eq 0) { return $null }
        $changed = $false
        foreach ($row in $grok) {
            if (-not $row) { continue }
            $heading = [string]$row.heading
            if (-not $heading) { continue }
            $token = ($heading -split '\s+', 2)[0]
            if (-not $token) { continue }
            $mid = $token.Trim().ToLowerInvariant()
            $lines = @(Get-BobTrayDigestWorkerLinesForMachine -Digest $digest -MachineId $mid)
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
      Also: the engine leaves when its exe parent is gone (BOB_TRAY_EXE_PID) so a crashed/killed tray never leaves an orphan engine.
      -OnAck/-OnExit/-OnRestart/-ParentGone are script blocks (the tray passes its functions; tests pass stubs).
    #>
    param([Parameter(Mandatory)][string]$Root, [scriptblock]$OnAck, [scriptblock]$OnExit, [scriptblock]$OnRestart, [scriptblock]$ParentGone)
    $f = Join-Path (Join-Path $Root 'run') 'tray-cmd.txt'
    $done = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $f) {
        $lines = @()
        try { $lines = @(Get-Content -LiteralPath $f -ErrorAction Stop) } catch { }
        try { Remove-Item -LiteralPath $f -Force -ErrorAction Stop } catch { }
        foreach ($l in $lines) {
            $cmd = ([string]$l).Trim().ToLowerInvariant()
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
