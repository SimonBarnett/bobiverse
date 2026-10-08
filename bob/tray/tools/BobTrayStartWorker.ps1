# BobTrayStartWorker.ps1 - tray side of "!startworker" (t810u). Dot-sourced by Watch-BobTray.ps1.
#
# The ear (service, session 0) authorises/caps/queues a request file; the tray - the one process that lives in the
# interactive session - launches the worker through the SAME function as the Agent / Plan click. Protocol (common\scripts\startworker.py):
#   <root>\run\startworker\tray.alive     heartbeat (FR #2697: ThreadPool/host timer every ~2 s; also touched on queue tick)
#   <root>\run\startworker\req-<id>.json  {id, mode, by, kind, ts, expires}  written atomically by the ear
#   <root>\run\startworker\res-<id>.json  {id, ok, reason, pid}               audit trail written here
# A request is DELETED before it is acted on (at-most-once) and ignored once expired. No credentials in any file.

function Get-BobTrayStartWorkerDir {
    param([Parameter(Mandatory)][string]$Root)
    return (Join-Path (Join-Path $Root 'run') 'startworker')
}

function Write-BobTrayAlive {
    param([Parameter(Mandatory)][string]$Dir)
    try {
        if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Force -Path $Dir | Out-Null }
        $f = Join-Path $Dir 'tray.alive'
        Set-Content -LiteralPath $f -Value ('{0} pid={1}' -f [datetime]::UtcNow.ToString('o'), $PID) -Encoding ASCII
        return $true
    }
    catch { return $false }
}

function Invoke-BobTrayStartWorkerQueue {
    <#
    .SYNOPSIS
      One tick: heartbeat, then consume every req-*.json. -Launch is { param($mode) ... return pid } (Start-BobTrayWorkerExe in the tray).
    .OUTPUTS
      One object per request: id, ok, reason, mode, pid.
    #>
    param(
        [Parameter(Mandatory)][string]$Dir,
        [Parameter(Mandatory)][scriptblock]$Launch,
        [scriptblock]$Log = { param($m) },
        [datetime]$Now = [datetime]::UtcNow
    )
    [void](Write-BobTrayAlive -Dir $Dir)
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
            $expires = [DateTimeOffset]::FromUnixTimeSeconds([int64]$req.expires).UtcDateTime
            if ($mode -notin @('agent', 'plan')) { $reason = 'bad-mode' }
            elseif ($Now -gt $expires) { $reason = 'expired' }
            elseif ((Get-BobTrayWorkerCapRefusal -Mode $mode)) { $reason = 'cap' }
            else {
                try {
                    $pidOut = [int](@(& $Launch $mode)[-1])
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
    # FR #3181: IRC-joined agent seats only (Plan/key-dialog never count).
    $n = Measure-BobTrayIrcAgentSeats
    if ($n -ge $cap) { return ('Max {0} workers ({1} IRC-joined agent seats). Close a worker window first.' -f $cap, $n) }
    return ''
}

# FR #2556: when reclaiming over HARD_MAX_WORKERS, kill SEAT ROOT trees only.
# Never: Get-CimInstance ... | Sort ProcessId | Select -Skip N | Stop-Process
# (onefile = bootloader+child same name; Skip-N by flat PID kills whole seats).
function Stop-BobWorkerSeatTrees {
  param([int[]]$RootPids)
  foreach ($root in $RootPids) {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.ProcessId -eq $root -or $_.ParentProcessId -eq $root } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  }
}
