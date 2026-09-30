# FR #345 (pairs AgentMonitor #97): tray-side watch seat slot / IRC home helpers.
# Dot-source from Watch-BobTray / Start-BobWatchWorker / tests.
# Never starts live monitors from this file alone.

function Get-BobWatchSeatKindName {
    param([ValidateSet('cursor', 'grok')][string]$Kind = 'grok')
    return $Kind.ToLowerInvariant()
}

function Get-BobWatchProfileRoot {
    param([string]$ProfileRoot = '')
    if ($ProfileRoot) { return [IO.Path]::GetFullPath($ProfileRoot) }
    if ($env:BOB_WATCH_SEAT_PROFILE_ROOT) {
        return [IO.Path]::GetFullPath($env:BOB_WATCH_SEAT_PROFILE_ROOT)
    }
    return [IO.Path]::GetFullPath($env:USERPROFILE)
}

function Get-BobWatchSeatHomePath {
    param(
        [ValidateSet('cursor', 'grok')][string]$Kind = 'grok',
        [int]$Slot = 1,
        [string]$ProfileRoot = ''
    )
    $k = Get-BobWatchSeatKindName -Kind $Kind
    $root = Get-BobWatchProfileRoot -ProfileRoot $ProfileRoot
    $base = Join-Path $root ('.agentic-irc-watch-{0}' -f $k)
    if ($Slot -le 1) { return [IO.Path]::GetFullPath($base) }
    return [IO.Path]::GetFullPath(($base + '-' + $Slot))
}

function Get-BobWatchSeatStatePath {
    param(
        [ValidateSet('cursor', 'grok')][string]$Kind = 'grok',
        [int]$Slot = 1,
        [string]$ProfileRoot = ''
    )
    $k = Get-BobWatchSeatKindName -Kind $Kind
    $root = Get-BobWatchProfileRoot -ProfileRoot $ProfileRoot
    $dir = Join-Path $root ('.grok\agent-health\watch-{0}-{1}' -f $k, $Slot)
    return Join-Path $dir 'state.json'
}

function Get-BobWatchSeatLogPath {
    param(
        [int]$Slot = 1,
        [string]$ProfileRoot = ''
    )
    $root = Get-BobWatchProfileRoot -ProfileRoot $ProfileRoot
    $desk = Join-Path $root 'Desktop\Watch-AgentHealth'
    if ($Slot -le 1) { return Join-Path $desk 'Watch-AgentHealth.log' }
    return Join-Path $desk ('Watch-AgentHealth-{0}.log' -f $Slot)
}

function Test-BobWatchHomeInUse {
    param(
        [string]$SeatHome,
        [int]$ExcludePid = 0
    )
    if (-not $SeatHome) { return $false }
    $full = [IO.Path]::GetFullPath($SeatHome).TrimEnd('\')
    $esc = [regex]::Escape($full)
    $rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $cl = [string]$_.CommandLine
            if (-not $cl) { return $false }
            if ($ExcludePid -gt 0 -and [int]$_.ProcessId -eq $ExcludePid) { return $false }
            # live watch worker or irc for this home
            if ($cl -match 'Watch-AgentHealth\.ps1' -and $cl -match [regex]::Escape($full)) { return $true }
            if (($cl -match 'irc_agent\.py' -or $cl -match 'irc_listen\.py') -and $cl -match $esc) { return $true }
            return $false
        })
    return ($rows.Count -gt 0)
}

function Resolve-BobWatchNextFreeSlot {
    param(
        [ValidateSet('cursor', 'grok')][string]$Kind = 'grok',
        [int]$MaxSlot = 16,
        [int]$ExcludePid = 0
    )
    for ($s = 1; $s -le $MaxSlot; $s++) {
        $seatHomePath = Get-BobWatchSeatHomePath -Kind $Kind -Slot $s
        if (-not (Test-BobWatchHomeInUse -SeatHome $seatHomePath -ExcludePid $ExcludePid)) {
            return [pscustomobject]@{
                Slot    = $s
                IrcHome = $seatHomePath
                Kind    = (Get-BobWatchSeatKindName -Kind $Kind)
            }
        }
    }
    throw ("All {0} watch-{1} slots are in use." -f $MaxSlot, $Kind)
}

function Read-BobWatchSeatState {
    param([string]$StatePath)
    if (-not $StatePath -or -not (Test-Path -LiteralPath $StatePath)) { return $null }
    try {
        return (Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json)
    }
    catch { return $null }
}

function Get-BobWatchSeatNickFromHome {
    param([string]$IrcHome)
    if (-not $IrcHome) { return '' }
    $coord = Join-Path $IrcHome 'coordinator.pid'
    if (-not (Test-Path -LiteralPath $coord)) { return '' }
    foreach ($line in @(Get-Content -LiteralPath $coord -ErrorAction SilentlyContinue)) {
        if ($line -match '^nick=(.+)$') { return $Matches[1].Trim() }
    }
    return ''
}

function Get-BobWatchMachineId {
    $mid = [string]$env:BOB_MACHINE_ID
    if (-not $mid) { $mid = [string]$env:COMPUTERNAME }
    if ($mid) { return $mid.ToLowerInvariant() }
    return 'unknown'
}

function Test-BobWatchSeatNickUnique {
    param(
        [string]$Nick,
        [string]$OwnHome
    )
    if (-not $Nick) { return $false }
    $own = if ($OwnHome) { [IO.Path]::GetFullPath($OwnHome).TrimEnd('\') } else { '' }
    $k = Get-BobWatchSeatKindName -Kind 'grok'
    # scan both kinds' slot homes for coordinator nick collision
    foreach ($kind in @('grok', 'cursor')) {
        for ($s = 1; $s -le 16; $s++) {
            $h = Get-BobWatchSeatHomePath -Kind $kind -Slot $s
            $hf = [IO.Path]::GetFullPath($h).TrimEnd('\')
            if ($own -and $hf -eq $own) { continue }
            $n = Get-BobWatchSeatNickFromHome -IrcHome $h
            if ($n -and $n.Equals($Nick, [StringComparison]::OrdinalIgnoreCase)) {
                return $false
            }
        }
    }
    return $true
}

function Test-BobWatchSeatIdentityOk {
    <#
      FR #345: after start, seat must own ircHome + unique {machine}-{pid} nick.
      Channels: prefer #{machine}; allow #bobiverse/#agentic_irc if present in state.
    #>
    param(
        [ValidateSet('cursor', 'grok')][string]$Kind,
        [int]$Slot,
        [string]$ExpectedHome,
        [int]$TimeoutSec = 60
    )
    $expected = [IO.Path]::GetFullPath($ExpectedHome).TrimEnd('\')
    $statePath = Get-BobWatchSeatStatePath -Kind $Kind -Slot $Slot
    $mid = Get-BobWatchMachineId
    $deadline = (Get-Date).AddSeconds([Math]::Max(5, $TimeoutSec))
    $lastWhy = 'timeout waiting for state.json'
    while ((Get-Date) -lt $deadline) {
        $st = Read-BobWatchSeatState -StatePath $statePath
        if (-not $st) {
            $lastWhy = "missing state $statePath"
            Start-Sleep -Milliseconds 500
            continue
        }
        $seatHomePath = [string]$st.ircHome
        if (-not $seatHomePath) {
            $lastWhy = 'state.ircHome empty'
            Start-Sleep -Milliseconds 500
            continue
        }
        $hf = [IO.Path]::GetFullPath($seatHomePath).TrimEnd('\')
        if ($hf -ne $expected) {
            $lastWhy = "ircHome collision/wrong home got=$hf expected=$expected"
            return [pscustomobject]@{ ok = $false; reason = $lastWhy; state = $st; nick = '' }
        }
        $nick = [string]$st.ircNick
        if (-not $nick) { $nick = Get-BobWatchSeatNickFromHome -IrcHome $hf }
        if (-not $nick) {
            $lastWhy = 'nick missing'
            Start-Sleep -Milliseconds 500
            continue
        }
        if ($nick -notmatch ('^{0}-\d+$' -f [regex]::Escape($mid))) {
            # machine id may differ slightly; require -digits suffix at least
            if ($nick -notmatch '^[a-z0-9][a-z0-9_-]*-\d+$') {
                $lastWhy = "nick shape bad: $nick"
                return [pscustomobject]@{ ok = $false; reason = $lastWhy; state = $st; nick = $nick }
            }
        }
        if (-not (Test-BobWatchSeatNickUnique -Nick $nick -OwnHome $hf)) {
            $lastWhy = "nick not unique on box: $nick"
            return [pscustomobject]@{ ok = $false; reason = $lastWhy; state = $st; nick = $nick }
        }
        $chans = [string]$st.ircChannels
        $shop = '#' + $mid
        if ($chans -and $chans -notmatch [regex]::Escape($shop) -and $chans -notmatch '#') {
            $lastWhy = "channels missing shop $shop ($chans)"
            # soft: still ok if coordinator lists channels
        }
        return [pscustomobject]@{
            ok     = $true
            reason = 'ok'
            state  = $st
            nick   = $nick
            home   = $hf
            slot   = $Slot
        }
    }
    return [pscustomobject]@{ ok = $false; reason = $lastWhy; state = $null; nick = '' }
}

function Get-BobWatchSeatProcessRows {
    param([string]$IrcHome)
    if (-not $IrcHome) { return @() }
    $full = [IO.Path]::GetFullPath($IrcHome).TrimEnd('\')
    $esc = [regex]::Escape($full)
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $cl = [string]$_.CommandLine
            if (-not $cl) { return $false }
            if ($cl -match $esc -and (
                    $cl -match 'Watch-AgentHealth\.ps1' -or
                    $cl -match 'irc_agent\.py' -or
                    $cl -match 'irc_listen\.py' -or
                    $cl -match 'agent\.exe' -or
                    $cl -match 'cursor-agent'
                )) { return $true }
            return $false
        })
}

function Stop-BobWatchSeatByHome {
    <#
      Stop ONLY processes whose command line contains this seat's IrcHome.
      Refuses if another live seat shares the same home path.
    #>
    param(
        [string]$IrcHome,
        [string]$Reason = 'tray stop'
    )
    if (-not $IrcHome) {
        return [pscustomobject]@{ ok = $false; reason = 'no home'; killed = 0 }
    }
    $full = [IO.Path]::GetFullPath($IrcHome).TrimEnd('\')
    # collision: two state files pointing at same home with different slots
    $owners = @()
    foreach ($kind in @('grok', 'cursor')) {
        for ($s = 1; $s -le 16; $s++) {
            $sp = Get-BobWatchSeatStatePath -Kind $kind -Slot $s
            $st = Read-BobWatchSeatState -StatePath $sp
            if (-not $st -or -not $st.ircHome) { continue }
            $hf = [IO.Path]::GetFullPath([string]$st.ircHome).TrimEnd('\')
            if ($hf -eq $full) {
                $owners += [pscustomobject]@{ kind = $kind; slot = $s; path = $sp }
            }
        }
    }
    if ($owners.Count -gt 1) {
        return [pscustomobject]@{
            ok     = $false
            reason = ("refusing stop: ircHome shared by {0} seats" -f $owners.Count)
            killed = 0
            home   = $full
        }
    }
    $killed = 0
    foreach ($row in @(Get-BobWatchSeatProcessRows -IrcHome $full)) {
        try {
            Stop-Process -Id ([int]$row.ProcessId) -Force -ErrorAction Stop
            $killed++
        }
        catch { }
    }
    return [pscustomobject]@{
        ok     = $true
        reason = $Reason
        killed = $killed
        home   = $full
    }
}

function Write-BobTrayStartLog {
    param(
        [string]$Action,
        [hashtable]$Fields,
        [string]$ProfileRoot = ''
    )
    $root = Get-BobWatchProfileRoot -ProfileRoot $ProfileRoot
    $dir = Join-Path $root 'Desktop\Watch-AgentHealth'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $path = Join-Path $dir 'tray-start.log'
    # rolling: keep last ~500KB
    if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Length -gt 500KB)) {
        Move-Item -LiteralPath $path -Destination ($path + '.1') -Force -ErrorAction SilentlyContinue
    }
    $parts = @('{0:o}' -f [datetime]::UtcNow, $Action)
    $parts = @('{0:o} {1}' -f [datetime]::UtcNow, $Action)
    if ($Fields) {
        foreach ($k in ($Fields.Keys | Sort-Object)) {
            $parts += ('{0}={1}' -f $k, $Fields[$k])
        }
    }
    Add-Content -LiteralPath $path -Value ($parts -join ' ') -Encoding utf8
    return $path
}

function Get-BobWatchLiveSeatSummaries {
    param([ValidateSet('cursor', 'grok', 'all')][string]$Kind = 'all')
    $out = @()
    $kinds = if ($Kind -eq 'all') { @('grok', 'cursor') } else { @($Kind) }
    foreach ($k in $kinds) {
        for ($s = 1; $s -le 16; $s++) {
            $seatHomePath = Get-BobWatchSeatHomePath -Kind $k -Slot $s
            if (-not (Test-Path -LiteralPath $seatHomePath)) { continue }
            $st = Read-BobWatchSeatState -StatePath (Get-BobWatchSeatStatePath -Kind $k -Slot $s)
            $nick = if ($st -and $st.ircNick) { [string]$st.ircNick } else { Get-BobWatchSeatNickFromHome -IrcHome $seatHomePath }
            $inUse = Test-BobWatchHomeInUse -SeatHome $seatHomePath
            if (-not $inUse -and -not $nick) { continue }
            $out += [pscustomobject]@{
                kind    = $k
                slot    = $s
                ircHome = $seatHomePath
                nick    = $nick
                live    = $inUse
            }
        }
    }
    return $out
}

function Build-BobWatchSeatLaunchArgs {
    param(
        [string]$ScriptPath,
        [ValidateSet('cursor', 'grok')][string]$Kind = 'grok',
        [int]$Slot,
        [string]$IrcHome,
        [switch]$New,
        [string]$Model = '',
        [string]$Cwd = ''
    )
    $kindFlag = if ($Kind -eq 'grok') { '-Grok' } else { '-Cursor' }
    # Watch host stays Hidden (tray child). Agent TUI must be visible for human
    # interaction: AgentMonitor -Windows on => AgentTuiWindowStyle Normal.
    # CAST IRON (Simon 2026-09-27): never -Windows off from the tray Agents menu.
    $args = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', $ScriptPath,
        '-WatchWorker', $kindFlag,
        '-Windows', 'on',
        '-IrcHome', $IrcHome
    )
    if ($New) { $args += '-New' }
    if ($Cwd) { $args += @('-Cwd', $Cwd) }
    if ($Kind -eq 'cursor') {
        $m = if ($Model) { $Model } else { 'auto' }
        $args += @('-Model', $m)
    }
    return $args
}

