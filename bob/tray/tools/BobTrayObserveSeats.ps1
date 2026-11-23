#Requires -Version 5.1
# FR #9208 / #8568: park-Watch-only TipForm must still observe seat drops (compiled bob-tray.exe
# ObserveWorkerSeats is absent while clickfalse-park). Synthesize last-exit + GIVEUP; never restart seats.
# FR #9226: always heal disappeared run dirs (even when seat count did not drop — tray restart
# after OC console-close); classify console-closed vs external-kill from worker.log breadcrumbs.

function Get-BobTrayLiveSeatProcessCount {
    param([string]$MachineId = '')
    $n = 0
    try {
        foreach ($pr in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
            $cl = [string]$pr.CommandLine
            $nm = [string]$pr.Name
            if (-not $cl -and -not $nm) { continue }
            $isWorker = ($nm -match '(?i)^bob-worker') -or ($cl -match '(?i)bob-worker\.exe') -or ($cl -match '(?i)bob_worker\.py')
            if (-not $isWorker) { continue }
            if ($MachineId) {
                $mid = [string]$MachineId
                if ($cl -and ($cl -notmatch [regex]::Escape($mid)) -and ($cl -notmatch 'BOB_MACHINE_ID')) {
                    # still count when CommandLine omits mid (most wrappers set env only)
                }
            }
            $n++
        }
    } catch { }
    return [int]$n
}

function Get-BobTrayAssignJobKeyFromText {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return '' }
    $body = $Line
    $toks = $Line -split '\s+', 4
    if ($toks.Count -ge 4 -and $toks[0] -ieq 'FROM') { $body = $toks[3] }
    $m = [regex]::Match($body, '\b(FR|MRB|UAT|FIX)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+)\b', 'IgnoreCase')
    if (-not $m.Success) { return '' }
    return ($m.Groups[1].Value.ToUpperInvariant() + ' ' + $m.Groups[2].Value)
}

function Get-BobTrayDisappearedSeatReason {
    # FR #9226: prefer console-closed when worker.log shows CTRL_CLOSE / 0xC000013A.
    param([Parameter(Mandatory)][string]$RunDir)
    $wl = Join-Path $RunDir 'worker.log'
    if (-not (Test-Path -LiteralPath $wl)) { return @{ Reason = 'external-kill'; ExitCode = $null } }
    $tail = ''
    try {
        $fs = [IO.File]::Open($wl, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $len = [int][Math]::Min($fs.Length, 65536)
            if ($len -le 0) { return @{ Reason = 'external-kill'; ExitCode = $null } }
            $null = $fs.Seek(-1 * $len, [IO.SeekOrigin]::End)
            $buf = New-Object byte[] $len
            $read = $fs.Read($buf, 0, $len)
            $tail = [Text.Encoding]::UTF8.GetString($buf, 0, $read)
        } finally { $fs.Close() }
    } catch {
        try { $tail = Get-Content -LiteralPath $wl -Raw -ErrorAction Stop } catch { $tail = '' }
    }
    if (-not $tail) { return @{ Reason = 'external-kill'; ExitCode = $null } }
    $exitCode = $null
    if ($tail -match '(?i)console-closed|console-close exit|STATUS_CONTROL_C_EXIT|0xC000013A|\b3221225786\b') {
        if ($tail -match '(?i)exit_code[=:\s]+(-?\d+)') {
            try { $exitCode = [int64]$Matches[1] } catch { $exitCode = 3221225786 }
        } elseif ($tail -match '(?i)\b3221225786\b') {
            $exitCode = 3221225786
        } else {
            $exitCode = 3221225786
        }
        return @{ Reason = 'console-closed'; ExitCode = $exitCode }
    }
    return @{ Reason = 'external-kill'; ExitCode = $null }
}

function Invoke-BobTrayHandleDisappearedWorkerRuns {
    # FR #8568 / #9208 / #9226: dead worker-<mid>-<pid>-* run dirs without last-exit.json get
    # synthetic last-exit + GIVEUP (console-closed when log says so, else external-kill).
    # Never restarts seats.
    param(
        [Parameter(Mandatory)][string]$MachineId,
        [string]$RunRoot = ''
    )
    $mid = ([string]$MachineId).Trim().ToLowerInvariant()
    if (-not $mid) { return @{ Handled = 0; Giveups = 0 } }
    if (-not $RunRoot) {
        $local = [string]$env:LOCALAPPDATA
        if (-not $local) { return @{ Handled = 0; Giveups = 0 } }
        $RunRoot = Join-Path $local 'Bobiverse\worker\run'
    }
    if (-not (Test-Path -LiteralPath $RunRoot)) { return @{ Handled = 0; Giveups = 0 } }
    $handled = 0
    $giveups = 0
    foreach ($dir in @(Get-ChildItem -LiteralPath $RunRoot -Directory -Filter 'worker-*' -ErrorAction SilentlyContinue)) {
        try {
            $name = $dir.Name
            $parts = $name -split '-'
            if ($parts.Count -lt 4) { continue }
            if ($parts[0] -ine 'worker') { continue }
            $seatPidTok = $parts[$parts.Count - 2]
            $seatPid = 0
            if (-not [int]::TryParse($seatPidTok, [ref]$seatPid) -or $seatPid -le 0) { continue }
            $midPart = $name.Substring('worker-'.Length)
            $needle = '-' + $seatPidTok + '-'
            $pidAt = $midPart.LastIndexOf($needle, [StringComparison]::OrdinalIgnoreCase)
            if ($pidAt -le 0) { continue }
            $runMid = $midPart.Substring(0, $pidAt).ToLowerInvariant()
            if ($runMid -ne $mid) { continue }
            $alive = $false
            try {
                $null = Get-Process -Id $seatPid -ErrorAction Stop
                $alive = $true
            } catch {
                $alive = $false
            }
            if ($alive) { continue }
            $lastExit = Join-Path $dir.FullName 'last-exit.json'
            if (Test-Path -LiteralPath $lastExit) { continue }
            $jobKey = ''
            $lastFrom = Join-Path $dir.FullName 'last-from.txt'
            if (Test-Path -LiteralPath $lastFrom) {
                try { $jobKey = Get-BobTrayAssignJobKeyFromText -Line ([IO.File]::ReadAllText($lastFrom)) } catch { $jobKey = '' }
            }
            $cls = Get-BobTrayDisappearedSeatReason -RunDir $dir.FullName
            $reason = [string]$cls.Reason
            if (-not $reason) { $reason = 'external-kill' }
            $exitCode = $cls.ExitCode
            $nick = ($runMid + '-' + $seatPid)
            $obj = [ordered]@{
                reason     = $reason
                exit_code  = $exitCode
                raw_code   = $exitCode
                job_key    = $jobKey
                machine    = $runMid
                nick       = $nick
                kind       = ''
                agent_pid  = $seatPid
                synthetic  = $true
                via        = 'fr-9226-watch-disappeared-seat'
            }
            $json = ($obj | ConvertTo-Json -Compress)
            [IO.File]::WriteAllText($lastExit, $json + "`n", [Text.UTF8Encoding]::new($false))
            $handled++
            if (Get-Command Write-BobTrayLifecycleEvent -ErrorAction SilentlyContinue) {
                Write-BobTrayLifecycleEvent -Event 'seat-disappeared' -Fields @{
                    pid = $seatPid
                    nick = $nick
                    run = $name
                    job = $(if ($jobKey) { $jobKey } else { '(none)' })
                    reason = $reason
                    exit_code = $(if ($null -ne $exitCode) { [string]$exitCode } else { '' })
                    via = 'fr-9226-watch'
                }
            }
            if (-not $jobKey) { continue }
            $outbox = Join-Path $dir.FullName 'outbox.txt'
            $existing = ''
            if (Test-Path -LiteralPath $outbox) {
                try { $existing = [IO.File]::ReadAllText($outbox) } catch { $existing = '' }
            }
            if ($existing -match [regex]::Escape('GIVEUP ' + $jobKey) -or
                $existing -match [regex]::Escape('DONE ' + $jobKey) -or
                $existing -match [regex]::Escape('NACK ' + $jobKey)) { continue }
            $channel = $runMid
            $why = $reason
            $line = "PRIVMSG #$channel :GIVEUP $jobKey $why`r`n"
            [IO.File]::AppendAllText($outbox, $line, [Text.UTF8Encoding]::new($false))
            $giveups++
        } catch { }
    }
    return @{ Handled = $handled; Giveups = $giveups }
}

function Invoke-BobTrayObserveWorkerSeats {
    # FR #3180 / #8568 / #9208 / #9226: log seat drop; always heal disappeared runs; never launch seats.
    param(
        [Parameter(Mandatory)][string]$MachineId,
        [string]$StatePath = ''
    )
    $mid = ([string]$MachineId).Trim().ToLowerInvariant()
    if (-not $StatePath) {
        $local = [string]$env:LOCALAPPDATA
        if (-not $local) { return @{ Observed = $false } }
        $StatePath = Join-Path $local 'Bobiverse\tray-seat-observe.json'
    }
    $n = Get-BobTrayLiveSeatProcessCount -MachineId $mid
    $last = -1
    if (Test-Path -LiteralPath $StatePath) {
        try {
            $st = Get-Content -LiteralPath $StatePath -Raw -ErrorAction Stop | ConvertFrom-Json
            if ($null -ne $st.lastSeatCount) { $last = [int]$st.lastSeatCount }
        } catch { $last = -1 }
    }
    $dir = Split-Path -Parent $StatePath
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    # FR #9226: heal orphan run dirs every poll (tray restart after OC death never saw a drop).
    $r = Invoke-BobTrayHandleDisappearedWorkerRuns -MachineId $mid
    $handled = [int]$r.Handled
    $giveups = [int]$r.Giveups
    if ($last -lt 0) {
        @{ lastSeatCount = $n; ts = [datetime]::UtcNow.ToString('o'); machine = $mid } |
            ConvertTo-Json -Compress |
            Set-Content -LiteralPath $StatePath -Encoding utf8
        return @{ Observed = $true; Was = $last; Now = $n; Dropped = $false; Handled = $handled; Giveups = $giveups }
    }
    $dropped = $n -lt $last
    if ($dropped) {
        if (Get-Command Write-BobTrayLifecycleEvent -ErrorAction SilentlyContinue) {
            Write-BobTrayLifecycleEvent -Event 'seat-exit' -Fields @{
                action = 'not restarted'; was = $last; now = $n; via = 'fr-9226-watch'; handled = $handled; giveups = $giveups
            }
        }
    }
    @{ lastSeatCount = $n; ts = [datetime]::UtcNow.ToString('o'); machine = $mid } |
        ConvertTo-Json -Compress |
        Set-Content -LiteralPath $StatePath -Encoding utf8
    return @{ Observed = $true; Was = $last; Now = $n; Dropped = $dropped; Handled = $handled; Giveups = $giveups }
}