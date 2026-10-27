# BobTrayRecycleSeat.ps1 - FR #5059 elevated tray recycle of a named seat.
# Dot-sourced by Watch-BobTray.ps1. Ear queues req-*.json; tray stops+verifies then starts.
#
# Protocol (common\scripts\recycleseat.py):
#   <root>\run\recycleseat\req-<id>.json  {id, nick, by, kind, ts, expires}
#   <root>\run\recycleseat\res-<id>.json  {id, ok, reason, old_pid, new_pid}
# CAST IRON: if stop fails or target still alive, do NOT start a new seat.

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

function Invoke-BobTrayRecycleSeatQueue {
    <#
    .SYNOPSIS
      FR #5059: consume recycleseat req-*.json. Stop named seat, verify gone, then Launch.
      -Launch is { param() ... return pid } (Start-BobTrayWorkerExe -Mode agent).
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
    foreach ($f in $reqs) {
        $req = $null
        try { $req = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
        try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop } catch { continue }
        $id = [string]$f.BaseName.Substring(4)
        $seatNick = if ($req) { [string]$req.nick } else { '' }
        $reason = ''
        $ok = $false
        $oldPid = 0
        $newPid = 0
        $mayStart = $false
        if (-not $req) { $reason = 'unreadable' }
        else {
            $expires = [DateTimeOffset]::FromUnixTimeSeconds([int64]$req.expires).UtcDateTime
            if ($Now -gt $expires) { $reason = 'expired' }
            elseif (-not $seatNick) { $reason = 'bad-nick' }
            else {
                $oldPid = [int](Get-BobTraySeatMarkerPid -Nick $seatNick)
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
                        $mayStart = $false
                        $reason = 'still-alive'
                        Invoke-BobTrayRecycleSeatReportFailure -Root $Root -Site ('recycleseat.still-alive:' + $seatNick) -Exception ('pid=' + $oldPid)
                    } else {
                        $mayStart = $true
                    }
                    if ($mayStart) {
                        try {
                            $newPid = [int](@(& $Launch)[-1])
                            if ($newPid -gt 0) { $ok = $true; $reason = 'ok' } else { $reason = 'launch-failed' }
                        } catch {
                            $reason = 'launch-error: ' + $_.Exception.Message
                            Invoke-BobTrayRecycleSeatReportFailure -Root $Root -Site ('recycleseat.launch:' + $seatNick) -Exception $_.Exception
                        }
                    }
                }
            }
        }
        try {
            & $Log ('recycleseat {0}: ok={1} nick={2} old={3} new={4} reason={5} by={6}' -f $id, $ok, $seatNick, $oldPid, $newPid, $reason, $(if ($req) { [string]$req.by } else { '-' }))
        } catch { }
        try {
            $res = [ordered]@{ id = $id; ok = $ok; reason = $reason; nick = $seatNick; old_pid = $oldPid; new_pid = $newPid }
            Set-Content -LiteralPath (Join-Path $Dir ('res-{0}.json' -f $id)) -Value ($res | ConvertTo-Json -Compress) -Encoding ASCII
            Get-ChildItem -LiteralPath $Dir -Filter 'res-*.json' -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 |
                ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force } catch { } }
        } catch { }
        [pscustomobject]@{ id = $id; ok = $ok; reason = $reason; nick = $seatNick; old_pid = $oldPid; new_pid = $newPid }
    }
}
