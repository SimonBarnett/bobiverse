# BobTrayStartWorker.ps1 - tray side of "!startworker" (t810u). Dot-sourced by Watch-BobTray.ps1.
#
# The ear (service, session 0) authorises/caps/queues a request file; the tray - the one process that lives in the
# interactive session - launches the worker through the SAME function as the Agent / Plan click. Protocol (common\scripts\startworker.py):
#   <root>\run\startworker\tray.alive     heartbeat, touched every tick (the ear NACKs when it is stale = nobody logged in)
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

# t815u: hard cap - never more than 2 worker seats (agent or plan) per machine, counted from LIVE bob-worker*.exe processes
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

function Measure-BobTrayWorkerSeats {
    param([object[]]$Procs)
    # Only bob-worker*.exe seats (never Watch-AgentHealth / grok.exe watch seats) - FR #2523 / t815u.
    $w = @($Procs | Where-Object { $_.Name -match '^bob-worker(-[0-9a-f]+)?\.exe$' })
    $ids = @($w | ForEach-Object { [int]$_.ProcessId })
    return @($w | Where-Object { $ids -notcontains [int]$_.ParentProcessId }).Count
}

function Get-BobTrayWorkerCapRefusal {
    <# '' when another worker may start, else the short refusal text (tray dialog / log). -Procs is for tests. #>
    param([object[]]$Procs = $null)
    if ($null -eq $Procs) {
        $Procs = @(Get-CimInstance Win32_Process -Filter "Name like 'bob-worker%'" -ErrorAction SilentlyContinue |
                Select-Object ProcessId, ParentProcessId, Name)
    }
    $cap = $script:BobTrayHardMaxWorkers
    $n = Measure-BobTrayWorkerSeats -Procs $Procs
    if ($n -ge $cap) { return ('Max {0} workers ({1} already running). Close a worker window first.' -f $cap, $n) }
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
