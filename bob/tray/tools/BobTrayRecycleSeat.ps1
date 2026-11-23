# BobTrayRecycleSeat.ps1 - FR #5059 elevated tray recycle of a named seat.
# Dot-sourced by Watch-BobTray.ps1. Ear queues req-*.json; tray stops+verifies then starts.
#
# Protocol (common\scripts\recycleseat.py):
#   <root>\run\recycleseat\req-<id>.json  {id, nick, by, kind, ts, expires}
#   <root>\run\recycleseat\res-<id>.json  {id, ok, reason, old_pid, new_pid}
# FR #8864 monitor force-recycle (do not wait for the 2s tray tick):
#   . BobTrayStartWorker.ps1
#   . BobTrayRecycleSeat.ps1
#   write run\recycleseat\req-<id>.json (expires = now + 300s)
#   Invoke-BobTrayRecycleSeatQueue -Root <install> -Dir <run\recycleseat> -Launch { param($nick, $kind, $model) Start-BobTrayWorkerExe -Mode agent -Agent $kind -Model $model -Quiet -Restore -Trigger restore-after-recycle -SeatId $nick }
#
# CAST IRON: if stop fails or target still alive, do NOT start a new seat.
# FR #8403: when several reqs are pending, stop every seat first, then start the
# replacements (serialize stop+start) so the 2-seat cap cannot leave stopped seats
# with launch-failed; a restore launch is -Restore (net-zero) and bypasses the cap.

function Get-BobTrayRecycleSeatDir {
    param([Parameter(Mandatory)][string]$Root)
    return (Join-Path (Join-Path $Root 'run') 'recycleseat')
}

function Get-BobTraySeatMarkerPid {
    param([Parameter(Mandatory)][string]$Nick)
    $safe = ($Nick -replace '[^A-Za-z0-9_-]', '_')
    if (-not $safe) { return 0 }
    $la = [Environment]::GetFolderPath('LocalApplicationData')
    $p = Join-Path $la ("Bobiverse\worker\run\seats\{0}.irc.json" -f $safe)
    if (-not (Test-Path -LiteralPath $p)) { return 0 }
    try {
        $j = Get-Content -LiteralPath $p -Raw -ErrorAction Stop | ConvertFrom-Json
        return [int]($j.pid)
    } catch { return 0 }
}

function Get-BobTraySeatPidFromNick {
    # FR #6986 / recycleseat.resolve_recycle_pid: nick suffix is the worker pid.
    param([Parameter(Mandatory)][string]$Nick)
    if ($Nick -match '-([1-9][0-9]*)$') {
        return [int]$Matches[1]
    }
    return 0
}

function Resolve-BobTrayRecyclePid {
    param(
        [int]$MarkerPid,
        [Parameter(Mandatory)][string]$Nick
    )
    if ($MarkerPid -gt 0) { return [int]$MarkerPid }
    return [int](Get-BobTraySeatPidFromNick -Nick $Nick)
}

function Test-BobTrayPidAlive {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return $false }
    try {
        $p = Get-Process -Id $ProcessId -ErrorAction Stop
        return [bool]$p
    } catch { return $false }
}

function Invoke-BobTrayRecycleSeatReportFailure {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Site,
        $Exception
    )
    try {
        # Live tray -RepoRoot is the install root (C:\ai\bob), not bob\tray.
        foreach ($rel in @(
                'tray\src\Private\Invoke-BobMustReportFailure.ps1',
                'src\Private\Invoke-BobMustReportFailure.ps1'
            )) {
            $hf = Join-Path $Root $rel
            if (Test-Path -LiteralPath $hf) { . $hf; break }
        }
        if (-not (Get-Command Report-BobRuntimeFailure -ErrorAction SilentlyContinue)) {
            foreach ($rel in @(
                    'common\scripts\Report-BobRuntimeFailure.ps1',
                    'scripts\Report-BobRuntimeFailure.ps1'
                )) {
                $rf = Join-Path $Root $rel
                if (Test-Path -LiteralPath $rf) { . $rf; break }
            }
        }
        if (Get-Command Invoke-BobMustReportFailure -ErrorAction SilentlyContinue) {
            Invoke-BobMustReportFailure -Component 'tray' -Site $Site -Exception $Exception | Out-Null
            return
        }
        if (Get-Command Report-BobRuntimeFailure -ErrorAction SilentlyContinue) {
            Report-BobRuntimeFailure -Component 'tray' -Site $Site -Exception $Exception | Out-Null
        }
    } catch { }
}

function Get-BobTrayRecycleLaunchRefusal {
    <#
    .SYNOPSIS
      FR #8403 / #9346: why a restore Launch would return no pid (mirrors the Start-BobTrayWorkerExe
      gates). '' when a launch may proceed. A -Restore launch skips the 2-seat cap, so the
      refusal left is seats-off, empty-online.disabled, or a missing worker exe; the cap check
      remains as a guard for callers that do not pass -Restore.
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Mode = 'agent',
        [string]$Trigger = 'restore-after-recycle'
    )
    if ($Mode -eq 'agent' -and (Get-Command Test-BobTraySeatsOff -ErrorAction SilentlyContinue)) {
        if (Test-BobTraySeatsOff) { return 'seats-off' }
    }
    # FR #9346 / #9240: shared empty-online.disabled gate (fail-closed for restore-after-recycle).
    if (
        $Mode -eq 'agent' -and
        (Get-Command Test-BobTrayEmptyOnlineBlocksAutoStart -ErrorAction SilentlyContinue) -and
        (Test-BobTrayEmptyOnlineBlocksAutoStart -Root $Root -Trigger $Trigger)
    ) {
        return 'empty-online-disabled'
    }
    if (Get-Command Get-BobTrayWorkerCapRefusal -ErrorAction SilentlyContinue) {
        $capRefusal = Get-BobTrayWorkerCapRefusal -Mode $Mode
        if ($capRefusal) { return 'cap' }
    }
    $exe = Join-Path $Root 'worker\bob-worker.exe'
    if (-not (Test-Path -LiteralPath $exe)) { return 'worker-exe-missing' }
    return ''
}

function Invoke-BobTrayRecycleSeatQueue {
    <#
    .SYNOPSIS
      FR #5059: consume recycleseat req-*.json. Stop named seat, verify gone, then Launch.
      -Launch is { param() ... return pid } (Start-BobTrayWorkerExe -Mode agent).
    .NOTES
      FR #8403: serialize stop+start. Every pending seat is stopped (and verified gone) in a
      first pass; replacements are launched in a second pass. A restore launch that races
      sibling recycles would hit the 2-seat cap and report launch-failed while the other seats
      are still alive; stopping all first lets each replacement see the real post-stop count,
      and -Restore skips the cap so a batch recycle recovers the seat count instead of leaving
      later seats stopped for a later Ensure path to fill anonymously. A launch that still
      returns no pid is named (seats-off / cap / worker-exe-missing), never a bare launch-failed.
    #>
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Dir,
        [Parameter(Mandatory)][scriptblock]$Launch,
        [scriptblock]$Log = { param($m) },
        [datetime]$Now = [datetime]::UtcNow,
        [int]$VerifyWaitMs = 3000
    )
    if (-not (Test-Path -LiteralPath $Dir)) {
        New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    }
    $reqs = @(Get-ChildItem -LiteralPath $Dir -Filter 'req-*.json' -File -ErrorAction SilentlyContinue | Sort-Object Name)

    $rows = New-Object System.Collections.Generic.List[object]
    $toStart = New-Object System.Collections.Generic.List[object]

    # Phase 1: validate and stop every seat; collect the ones cleared to start.
    foreach ($f in $reqs) {
        $req = $null
        try { $req = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
        try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop } catch { continue }
        $id = [string]$f.BaseName.Substring(4)
        $seatNick = if ($req) { [string]$req.nick } else { '' }
        $by = if ($req) { [string]$req.by } else { '-' }
        $reason = ''
        $ok = $false
        $oldPid = 0
        $newPid = 0
        $mayStart = $false
        $clickedKind = ''
        $clickedModel = ''
        if (-not $req) { $reason = 'unreadable' }
        else {
            $expires = [DateTimeOffset]::FromUnixTimeSeconds([int64]$req.expires).UtcDateTime
            if ($Now -gt $expires) { $reason = 'expired' }
            elseif (-not $seatNick) { $reason = 'bad-nick' }
            else {
                $seatsOffCmd = Get-Command Test-BobTraySeatsOff -ErrorAction SilentlyContinue
                $seatsOff = $false
                if ($seatsOffCmd) { $seatsOff = [bool](Test-BobTraySeatsOff) }
                if ($seatsOff) {
                    # FR #7669: do not stop a live seat and do not start a replacement.
                    $reason = 'seats-off'
                }
                else {
                    # FR #7692: req.kind is who asked (chair/op), not the seat. Use the click record.
                    # FR #8321: restart with the clicked model too (paid stays paid, free stays free).
                    if (Get-Command Get-BobTrayClickedSeat -ErrorAction SilentlyContinue) {
                        $clickRec = Get-BobTrayClickedSeat -Root $Root -Nick $seatNick
                        if ($clickRec) {
                            $clickedKind = [string]$clickRec.Kind
                            $clickedModel = [string]$clickRec.Model
                        }
                    }
                    elseif (Get-Command Get-BobTrayClickedSeatKind -ErrorAction SilentlyContinue) {
                        $clickedKind = [string](Get-BobTrayClickedSeatKind -Root $Root -Nick $seatNick)
                    }
                    if (@('grok', 'cursor', 'opencode') -notcontains $clickedKind) {
                        # FR #7835: kind-unknown is the planned refuse (no click record).
                        # Do not file a tray RuntimeError. That opened a crash issue for a seat
                        # the tray correctly will not restart as a different kind.
                        $reason = 'kind-unknown'
                    }
                    else {
                        $oldPid = Resolve-BobTrayRecyclePid -MarkerPid ([int](Get-BobTraySeatMarkerPid -Nick $seatNick)) -Nick $seatNick
                        $found = $oldPid -gt 0
                        if (-not $found) {
                            $reason = 'not-found'
                        } else {
                            $stopOk = $true
                            try {
                                if (Get-Command Stop-BobWorkerSeatTrees -ErrorAction SilentlyContinue) {
                                    Stop-BobWorkerSeatTrees -RootPids @($oldPid)
                                } else {
                                    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                                        Where-Object { $_.ProcessId -eq $oldPid -or $_.ParentProcessId -eq $oldPid } |
                                        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                                }
                            } catch {
                                $stopOk = $false
                                $reason = 'stop-failed'
                                Invoke-BobTrayRecycleSeatReportFailure -Root $Root -Site ('recycleseat.stop:' + $seatNick) -Exception $_.Exception
                            }
                            $deadline = [datetime]::UtcNow.AddMilliseconds([Math]::Max(500, $VerifyWaitMs))
                            $still = $true
                            while ([datetime]::UtcNow -lt $deadline) {
                                $still = Test-BobTrayPidAlive -ProcessId $oldPid
                                if (-not $still) { break }
                                Start-Sleep -Milliseconds 200
                            }
                            $still = Test-BobTrayPidAlive -ProcessId $oldPid
                            # plan_recycle_action: may_start only when stop_ok and not still-alive and found
                            if (-not $stopOk) {
                                $mayStart = $false
                                if (-not $reason) { $reason = 'stop-failed' }
                            } elseif ($still) {
                                # FR #7688: still-alive is the planned refuse (plan_recycle_action).
                                # The seat did not die inside the verify window. Log reason=still-alive.
                                # Do not file a tray RuntimeError; that opened a crash issue for a live worker.
                                $mayStart = $false
                                $reason = 'still-alive'
                            } else {
                                $mayStart = $true
                            }
                        }
                    }
                }
            }
        }
        $row = [pscustomobject]@{ id = $id; ok = $ok; reason = $reason; nick = $seatNick; old_pid = $oldPid; new_pid = $newPid; by = $by; seatNick = $seatNick; clickedKind = $clickedKind; clickedModel = $clickedModel; mayStart = $mayStart }
        $rows.Add($row)
        if ($mayStart) { $toStart.Add($row) }
    }

    # Phase 2: launch every replacement (all stops are already done).
    foreach ($row in $toStart) {
        $seatNick = [string]$row.seatNick
        $clickedKind = [string]$row.clickedKind
        $clickedModel = [string]$row.clickedModel
        # FR #9346: refuse before Launch when empty-online.disabled blocks restore-after-recycle.
        # Only the kill-switch gate runs here; seats-off / cap / worker-exe-missing stay post-Launch
        # (Get-BobTrayRecycleLaunchRefusal) so stub Launch tests and -Restore cap skip still work.
        $blockEmpty = $false
        if (Get-Command Test-BobTrayEmptyOnlineBlocksAutoStart -ErrorAction SilentlyContinue) {
            try { $blockEmpty = [bool](Test-BobTrayEmptyOnlineBlocksAutoStart -Root $Root -Trigger 'restore-after-recycle') } catch { $blockEmpty = $false }
        }
        if ($blockEmpty) {
            $row.ok = $false
            $row.reason = 'empty-online-disabled'
            try {
                if (Get-Command Write-BobTrayUnrequestedSeatStartIntake -ErrorAction SilentlyContinue) {
                    [void](Write-BobTrayUnrequestedSeatStartIntake -Root $Root -Trigger 'restore-after-recycle' -Site 'Invoke-BobTrayRecycleSeatQueue')
                }
            } catch { }
            continue
        }
        # FR #7117: one retry if the first start returns no pid; never wait for a key.
        $tries = 0
        while ($tries -lt 2 -and -not $row.ok) {
            $tries++
            try {
                # FR #8864: last numeric pid; Write-Output log lines are not the pid.
                # Soft-dep: unit tests may load RecycleSeat without BobTrayStartWorker.ps1.
                $launchOut = @(& $Launch $seatNick $clickedKind $clickedModel)
                if (Get-Command Get-BobTrayLaunchPidFromOutput -ErrorAction SilentlyContinue) {
                    $newPid = [int](Get-BobTrayLaunchPidFromOutput -Output $launchOut)
                } else {
                    $newPid = 0
                    foreach ($item in @($launchOut)) {
                        if ($null -eq $item) { continue }
                        $n = 0
                        if ([int]::TryParse([string]$item, [ref]$n) -and $n -gt 0) { $newPid = $n }
                    }
                }
                if ($newPid -gt 0) { $row.ok = $true; $row.reason = 'ok'; $row.new_pid = $newPid }
                else {
                    # FR #8403: name the refusal (seats-off / cap / worker-exe-missing), never a bare launch-failed.
                    # FR #8864: one beat so a just-stopped seat drops out of the cap sample before the retry.
                    $refusal = Get-BobTrayRecycleLaunchRefusal -Root $Root
                    $row.reason = if ($refusal) { $refusal } else { 'launch-failed' }
                    if ($row.reason -eq 'cap' -and $tries -lt 2) { Start-Sleep -Milliseconds 500 }
                }
            } catch {
                $row.reason = 'launch-error: ' + $_.Exception.Message
                Invoke-BobTrayRecycleSeatReportFailure -Root $Root -Site ('recycleseat.launch:' + $seatNick) -Exception $_.Exception
                break
            }
        }
    }

    foreach ($row in $rows) {
        try {
            & $Log ('recycleseat {0}: ok={1} nick={2} old={3} new={4} reason={5} by={6} trigger=restore-after-recycle' -f $row.id, $row.ok, $row.nick, $row.old_pid, $row.new_pid, $row.reason, $row.by)
        } catch { }
        try {
            $res = [ordered]@{ id = $row.id; ok = $row.ok; reason = $row.reason; nick = $row.nick; old_pid = $row.old_pid; new_pid = $row.new_pid }
            Set-Content -LiteralPath (Join-Path $Dir ('res-{0}.json' -f $row.id)) -Value ($res | ConvertTo-Json -Compress) -Encoding ASCII
        } catch { }
    }
    # keep the audit trail short
    try {
        Get-ChildItem -LiteralPath $Dir -Filter 'res-*.json' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
            ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force } catch { } }
    } catch { }
    $rows.ToArray()
}
