<#
.SYNOPSIS
  Start grok agent.exe or Cursor agent.cmd; watch the agent process; forward IRC FROM lines when the agent's listener exists.

.DESCRIPTION
  Simon #bobiverse 2026-09-22: --grok / --cursor. Persist session id (resume, no full skill reload).
  Does not start, stop, or health-check irc_listen — the agent connects to IRC per agentic-irc.
  Monitor tails $IrcHome/irc.log (agent debug firehose) and resume-forwards each PRIVMSG as FROM into the agent.
  The agent only handles messages the monitor passes; it does not run or duplicate this monitor.
  Own IRC home only (.agentic-irc-watch-*). Does not touch cursor / cursor-2 / bobiverse Watch.
  Multiple clients per box: next free slot (watch-cursor, watch-cursor-2, …). Never restart a live seat.
  TUI exit: QUIT that slot only. Start another client; do not reconnect the same one.
  Does not stamp UAT. Does not send !bobiverse.

.EXAMPLE
  Desktop\Watch-AgentHealth.cmd cursor
  Desktop\Watch-AgentHealth.cmd cursor new
  Desktop\Watch-AgentHealth.cmd grok
  Desktop\Watch-AgentHealth.cmd grok new

  Direct .\Watch-AgentHealth.ps1 fails when execution policy is Restricted; use .cmd or -ExecutionPolicy Bypass.
  Visible by default (no on flag). -Windows off: hidden watch worker and hidden agent TUI; log file still receives lines. One-shot agent -p forwards stay hidden.
#>
[CmdletBinding(DefaultParameterSetName = 'none')]
param(
    [Parameter(ParameterSetName = 'grok')]
    [switch]$Grok,

    [Parameter(ParameterSetName = 'cursor')]
    [switch]$Cursor,

    [switch]$New,

    [switch]$WatchWorker,

    [ValidateSet('on', 'off')]
    [string]$Windows = 'on',

    [string]$Cwd,
    [string]$IrcHome,
    [int]$PollSeconds = 15,
    [int]$CrashBackoffSeconds = 20,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'

$script:AgentTuiWindowStyle = $(if ($Windows -eq 'on') { 'Normal' } else { 'Hidden' })

if (-not $Grok -and -not $Cursor) {
    throw 'Pass --grok (agent.exe) or --cursor (agent.cmd).'
}

function Resolve-AgentWorkspace {
    param(
        [string]$Requested,
        [switch]$Explicit
    )
    if ($Explicit -and $Requested) {
        return [IO.Path]::GetFullPath($Requested)
    }
    $leaf = 'ai'
    foreach ($letter in @('D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z')) {
        $root = '{0}:\' -f $letter
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $candidate = Join-Path $root $leaf
        if (Test-Path -LiteralPath $candidate) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    foreach ($letter in @('D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z')) {
        $root = '{0}:\' -f $letter
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $candidate = Join-Path $root $leaf
        New-Item -ItemType Directory -Force -Path $candidate | Out-Null
        return [IO.Path]::GetFullPath($candidate)
    }
    throw 'No drive D:..Z: found to use or create \ai.'
}

$CwdExplicit = $PSBoundParameters.ContainsKey('Cwd') -and $Cwd
$Cwd = Resolve-AgentWorkspace -Requested $Cwd -Explicit:$CwdExplicit

$script:KindName = $(if ($Cursor) { 'cursor' } else { 'grok' })
$script:StateDir = Join-Path $env:USERPROFILE '.grok\agent-health'
$script:ClientSlot = 1
$script:StatePath = Join-Path $script:StateDir ("state-{0}.json" -f $script:KindName)
$script:WorkerPidPath = Join-Path $script:StateDir ("watch-worker-{0}.pid" -f $script:KindName)
$script:IrcHomeExplicit = $PSBoundParameters.ContainsKey('IrcHome') -and $IrcHome
if (-not $IrcHome) {
    $IrcHome = Join-Path $env:USERPROFILE ('.agentic-irc-watch-{0}' -f $script:KindName)
}

function Get-WatchSlotPaths {
    param([int]$Slot)
    $suffix = if ($Slot -le 1) { '' } else { '-{0}' -f $Slot }
    return [pscustomobject]@{
        Slot          = $Slot
        Suffix        = $suffix
        StatePath     = Join-Path $script:StateDir ('state-{0}{1}.json' -f $script:KindName, $suffix)
        WorkerPidPath = Join-Path $script:StateDir ('watch-worker-{0}{1}.pid' -f $script:KindName, $suffix)
        IrcHome       = Join-Path $env:USERPROFILE ('.agentic-irc-watch-{0}{1}' -f $script:KindName, $suffix)
    }
}

function Test-WatchSlotLive {
    param([int]$Slot)
    $paths = Get-WatchSlotPaths -Slot $Slot
    if (Test-Path -LiteralPath $paths.WorkerPidPath) {
        try {
            $old = [int](Get-Content -LiteralPath $paths.WorkerPidPath -Raw)
        }
        catch { $old = 0 }
        if ($old -gt 0 -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
            return $true
        }
    }
    $watchHome = [IO.Path]::GetFullPath($paths.IrcHome).TrimEnd('\')
    $irc = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
            $cl = [string]$_.CommandLine
            if ($cl -notmatch 'irc_agent\.py') { return $false }
            $idx = $cl.IndexOf($watchHome, [StringComparison]::OrdinalIgnoreCase)
            if ($idx -lt 0) { return $false }
            $end = $idx + $watchHome.Length
            if ($end -ge $cl.Length) { return $true }
            return ($cl[$end] -match '[\s\\/"]')
        })
    return ($irc.Count -gt 0)
}

function Resolve-WatchSlotFromIrcHome {
    param([string]$WatchHomePath)
    $leaf = Split-Path -Path $WatchHomePath -Leaf
    $prefix = '.agentic-irc-watch-{0}' -f $script:KindName
    if ($leaf -eq $prefix) { return 1 }
    $m = [regex]::Match($leaf, ('^{0}-(\d+)$' -f [regex]::Escape($prefix)))
    if ($m.Success) { return [int]$m.Groups[1].Value }
    return 1
}

function Bind-WatchClientSlot {
    if ($script:IrcHomeExplicit) { return $null }
    $chosen = 0
    for ($i = 1; $i -le 8; $i++) {
        if (-not (Test-WatchSlotLive -Slot $i)) {
            $chosen = $i
            break
        }
    }
    if ($chosen -le 0) {
        throw 'Too many watch clients on this box (8). Do not restart a live seat; start a new one only if a slot is free.'
    }
    return (Get-WatchSlotPaths -Slot $chosen)
}

function Write-WatchLog {
    param([string]$Message)
    $line = '{0:o} {1}' -f [datetime]::UtcNow, $Message
    Add-Content -LiteralPath $script:LogFile -Value $line -Encoding utf8
    Write-Host $line
}

function Read-WatchState {
    if (-not (Test-Path -LiteralPath $script:StatePath)) { return $null }
    try {
        return (Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json)
    }
    catch { return $null }
}

function Write-WatchState {
    param($Obj)
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($script:StatePath, ($Obj | ConvertTo-Json -Depth 6), $utf8)
}

function Reset-WatchSessionForNew {
    param($State)
    $State.sessionId = [guid]::NewGuid().ToString()
    $State.seenSession = $false
    $State.rootPid = 0
    if ($State.PSObject.Properties['ircLogOffset']) {
        $State.PSObject.Properties.Remove('ircLogOffset')
    }
    if ($State.PSObject.Properties['listenOffset']) {
        $State.PSObject.Properties.Remove('listenOffset')
    }
    if ($State.PSObject.Properties.Name -contains 'cursorPrintOnly') {
        $State.PSObject.Properties.Remove('cursorPrintOnly')
    }
    if ($State.PSObject.Properties.Name -contains 'cursorSessionValid') {
        $State.PSObject.Properties.Remove('cursorSessionValid')
    }
    if ($State.PSObject.Properties.Name -contains 'cursorChatCreated') {
        $State.PSObject.Properties.Remove('cursorChatCreated')
    }
    return $State
}

function Get-GrokAgentPath {
    $p = Join-Path $env:USERPROFILE '.grok\bin\agent.exe'
    if (Test-Path -LiteralPath $p) { return (Resolve-Path $p).Path }
    $cmd = Get-Command agent.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw 'grok agent.exe not found (~/.grok/bin/agent.exe).'
}

function Get-CursorAgentCmd {
    $p = Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd'
    if (Test-Path -LiteralPath $p) { return (Resolve-Path $p).Path }
    $cmd = Get-Command agent.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw 'cursor agent.cmd not found (%LOCALAPPDATA%\cursor-agent\agent.cmd).'
}

function Get-CursorAgentPs1 {
    $cmd = Get-CursorAgentCmd
    $ps1 = Join-Path ([IO.Path]::GetDirectoryName($cmd)) 'cursor-agent.ps1'
    if (Test-Path -LiteralPath $ps1) { return (Resolve-Path $ps1).Path }
    return $cmd
}

function New-CursorChatSessionId {
    param(
        [string]$AgentCmd,
        [string]$WorkDir
    )
    $outFile = Join-Path $script:StateDir 'create-chat.out.txt'
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $valid = $false
    $sid = [guid]::NewGuid().ToString()
    try {
        $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList @(
            '/c', "`"$AgentCmd`" create-chat > `"$outFile`" 2>&1"
        ) -WorkingDirectory $WorkDir -WindowStyle Hidden -Wait -PassThru
        if ($proc.ExitCode -eq 0 -and (Test-Path -LiteralPath $outFile)) {
            $out = Get-Content -LiteralPath $outFile -Raw -Encoding UTF8
            if ($out -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') {
                $sid = $Matches[1].ToLower()
                $valid = $true
            }
        }
    }
    finally { $ErrorActionPreference = $prev }
    if (-not $valid) {
        Write-WatchLog 'create-chat failed - local session id only; agent -p will not use --resume until a run succeeds'
    }
    return [pscustomobject]@{ SessionId = $sid; ServerChat = $valid }
}

function Set-CursorPrintOnlyMode {
    param($State, [switch]$Enable)
    if ($Enable) {
        $State | Add-Member -NotePropertyName 'cursorPrintOnly' -NotePropertyValue $true -Force
        $State.rootPid = 0
        Write-WatchLog 'cursor print-only mode (no TUI relaunch); IRC still forwarded with agent -p'
    }
    else {
        if ($State.PSObject.Properties.Name -contains 'cursorPrintOnly') {
            $State.PSObject.Properties.Remove('cursorPrintOnly')
        }
    }
    return $State
}

function Test-CursorPrintOnlyMode {
    param($State)
    return ($State.PSObject.Properties.Name -contains 'cursorPrintOnly') -and [bool]$State.cursorPrintOnly
}

function Get-WatchForwardScriptLeaf {
    if ($script:ClientSlot -le 1) { return 'forward-cursor.ps1' }
    return ('forward-cursor-{0}.ps1' -f $script:ClientSlot)
}

function Set-WatchForwardPaths {
    $leaf = Get-WatchForwardScriptLeaf
    $script:ForwardScriptPath = Join-Path $script:StateDir $leaf
    if ($script:ClientSlot -le 1) {
        $script:ForwardPromptPath = Join-Path $script:StateDir 'forward-cursor.prompt.txt'
    }
    else {
        $script:ForwardPromptPath = Join-Path $script:StateDir ('forward-cursor-{0}.prompt.txt' -f $script:ClientSlot)
    }
}

function Test-CursorAgentForwardBusy {
    param([string]$SessionId)
    $sid = ([string]$SessionId).Trim()
    $sidPat = if ($sid) { [regex]::Escape($sid) } else { '' }
    $fwdLeaf = [regex]::Escape((Get-WatchForwardScriptLeaf))
    $rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    foreach ($row in $rows) {
        $cl = [string]$row.CommandLine
        if ([string]$row.Name -eq 'powershell.exe' -and $cl -match $fwdLeaf) {
            return $true
        }
        if ($sidPat -and $cl -match 'cursor-agent' -and $cl -match $sidPat -and $cl -match ' -p ') {
            return $true
        }
    }
    return $false
}

function Test-CursorAgentNodeIsProtected {
    param([string]$CommandLine)
    $cl = [string]$CommandLine
    if ($cl -match 'Git task ') { return $true }
    if ($cl -match 'long-running-background-tasks') { return $true }
    return $false
}

function Find-CursorAgentPidBySession {
    param([string]$SessionId)
    $sid = ([string]$SessionId).Trim()
    if (-not $sid) { return 0 }
    $pat = [regex]::Escape($sid)
    foreach ($procName in @('node.exe', 'Cursor.exe')) {
        $rows = @(Get-CimInstance Win32_Process -Filter "Name='$procName'" -ErrorAction SilentlyContinue)
        foreach ($row in $rows) {
            $cl = [string]$row.CommandLine
            if ($cl -match 'cursor-agent' -and $cl -match $pat) {
                return [int]$row.ProcessId
            }
        }
    }
    return 0
}

function Find-CursorInteractiveAgentUnderRoot {
    param([int]$RootPid)
    if ($RootPid -le 0) { return 0 }
    foreach ($id in (Get-DescendantPids -RootPid $RootPid)) {
        $row = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if (-not $row) { continue }
        $cl = [string]$row.CommandLine
        if ($cl -match 'cursor-agent' -and $cl -notmatch ' -p ') {
            return [int]$id
        }
    }
    return 0
}

function Sync-CursorSessionFromComposer {
    param(
        $State,
        [int]$ComposerPid
    )
    if ($ComposerPid -le 0) { return $State }
    $row = Get-CimInstance Win32_Process -Filter "ProcessId=$ComposerPid" -ErrorAction SilentlyContinue
    if (-not $row) { return $State }
    $cl = [string]$row.CommandLine
    if ($cl -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') {
        $found = $Matches[1].ToLower()
        if ([string]$State.sessionId -ne $found) {
            Write-WatchLog "cursor composer session id=$found (was $($State.sessionId))"
            $State.sessionId = $found
        }
        $State | Add-Member -NotePropertyName 'cursorSessionValid' -NotePropertyValue $true -Force
    }
    return $State
}

function Get-CommitHeadroomGb {
    try {
        $cp = Get-Counter '\Memory\Committed Bytes', '\Memory\Commit Limit' -ErrorAction Stop
        $cb = $cp.CounterSamples | Where-Object { $_.Path -like '*Committed Bytes*' } | Select-Object -ExpandProperty CookedValue
        $cl = $cp.CounterSamples | Where-Object { $_.Path -like '*Commit Limit*' } | Select-Object -ExpandProperty CookedValue
        return [pscustomobject]@{
            FreeGb  = [math]::Round(($cl - $cb) / 1GB, 2)
            LimitGb = [math]::Round($cl / 1GB, 2)
        }
    }
    catch {
        return [pscustomobject]@{ FreeGb = -1; LimitGb = -1 }
    }
}

function Get-CursorTuiMissNodeWhy {
    $head = Get-CommitHeadroomGb
    if ($head.FreeGb -ge 0 -and $head.FreeGb -lt 0.5) { return 'low commit' }
    return 'launcher exited or node never appeared (not cmd.exe prompt-on-argv)'
}

function Write-CursorAgentProcessSnapshot {
    param([string]$Reason)
    $rows = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue | Where-Object {
            [string]$_.CommandLine -match 'cursor-agent'
        })
    $head = Get-CommitHeadroomGb
    Write-WatchLog ("{0} commitFreeGb={1} limitGb={2} cursor-agentNodes={3}" -f $Reason, $head.FreeGb, $head.LimitGb, $rows.Count)
    foreach ($row in $rows) {
        $ws = [math]::Round($row.WorkingSetSize / 1MB, 0)
        $mode = if ([string]$row.CommandLine -match ' -p ') { '-p' } elseif ([string]$row.CommandLine -match '--resume') { 'resume' } else { 'other' }
        $sid = '?'
        if ([string]$row.CommandLine -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') {
            $sid = $Matches[1].Substring(0, 8)
        }
        Write-WatchLog ("  node pid={0} wsMb={1} mode={2} session~={3}" -f $row.ProcessId, $ws, $mode, $sid)
    }
}

function Stop-CursorAgentNodesForSession {
    param([string]$SessionId)
    $sid = ([string]$SessionId).Trim()
    if (-not $sid) { return 0 }
    $pat = [regex]::Escape($sid)
    $stopped = 0
    $rows = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue | Where-Object {
            [string]$_.CommandLine -match 'cursor-agent'
        })
    foreach ($row in $rows) {
        $cl = [string]$row.CommandLine
        if ($cl -notmatch $pat) { continue }
        if (Test-CursorAgentNodeIsProtected -CommandLine $cl) {
            Write-WatchLog ("prune skip protected cursor-agent pid={0} (Git/fleet job)" -f $row.ProcessId)
            continue
        }
        Write-WatchLog ("prune watch-session cursor-agent pid={0} session={1}" -f $row.ProcessId, $sid.Substring(0, 8))
        Stop-WatchedTree -RootPid ([int]$row.ProcessId)
        $stopped++
    }
    return $stopped
}

function Stop-OrphanCursorWatchForwards {
    $stopped = 0
    $rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    foreach ($row in $rows) {
        $cl = [string]$row.CommandLine
        if (Test-CursorAgentNodeIsProtected -CommandLine $cl) { continue }
        $fwdLeaf = [regex]::Escape((Get-WatchForwardScriptLeaf))
        if ([string]$row.Name -eq 'powershell.exe' -and $cl -match $fwdLeaf) {
            Write-WatchLog ("prune hung watch forward powershell pid={0} slot={1}" -f $row.ProcessId, $script:ClientSlot)
            Stop-WatchedTree -RootPid ([int]$row.ProcessId)
            $stopped++
            continue
        }
        if ([string]$row.Name -eq 'node.exe' -and $cl -match 'cursor-agent' -and $cl -match 'worker-server') {
            $parent = Get-Process -Id ([int]$row.ParentProcessId) -ErrorAction SilentlyContinue
            if (-not $parent) {
                Write-WatchLog ("prune orphan worker-server pid={0}" -f $row.ProcessId)
                Stop-Process -Id $row.ProcessId -Force -ErrorAction SilentlyContinue
                $stopped++
            }
        }
    }
    return $stopped
}

function Test-CursorUseResumeCli {
    param($State)
    if ($State.PSObject.Properties.Name -contains 'cursorSessionValid' -and [bool]$State.cursorSessionValid) {
        return $true
    }
    if ([bool]$State.seenSession -and -not [string]::IsNullOrWhiteSpace([string]$State.sessionId)) {
        return $true
    }
    return $false
}

function Test-CursorUseResumeForTui {
    param($State, [switch]$ResumeShortcut)
    if (Test-CursorUseResumeCli -State $State) {
        if ($ResumeShortcut -and -not (($State.PSObject.Properties.Name -contains 'cursorSessionValid') -and [bool]$State.cursorSessionValid)) {
            Write-WatchLog 'cursor Resume: TUI/agent --resume with stored session id'
        }
        return $true
    }
    if ($ResumeShortcut) {
        Write-WatchLog 'cursor Resume: no stored session; TUI starts fresh'
    }
    return $false
}

function Resolve-CursorWatchRootPid {
    param(
        [string]$SessionId,
        [int]$LauncherPid
    )
    if ($LauncherPid -gt 0) {
        $row = Get-CimInstance Win32_Process -Filter "ProcessId=$LauncherPid" -ErrorAction SilentlyContinue
        if ($row) {
            $cl = [string]$row.CommandLine
            if ($cl -match 'cursor-agent' -and $cl -notmatch ' -p ') {
                return [int]$LauncherPid
            }
        }
        $under = Find-CursorInteractiveAgentUnderRoot -RootPid $LauncherPid
        if ($under -gt 0) { return $under }
    }
    $bySession = Find-CursorAgentPidBySession -SessionId $SessionId
    if ($bySession -gt 0) { return $bySession }
    return 0
}

function Test-ForbiddenIrcHome {
    param([string]$ResolvedHome)
    $full = [IO.Path]::GetFullPath($ResolvedHome).TrimEnd('\')
    $ban = @(
        (Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
        (Join-Path $env:USERPROFILE '.agentic-irc-cursor-2'),
        (Join-Path $env:USERPROFILE '.agentic-irc-bobiverse')
    ) | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }
    return ($ban -contains $full)
}

function Initialize-WatchIrcHome {
    param($State)
    $resolved = [IO.Path]::GetFullPath($IrcHome)
    if (Test-ForbiddenIrcHome -ResolvedHome $resolved) {
        throw "Refusing IrcHome $resolved (talk-seat / Watch home). Use .agentic-irc-watch-*."
    }
    $State.ircHome = $resolved
    return $State
}

function Get-WatchIrcAgentRows {
    param([string]$ResolvedHome)
    $watchHome = [IO.Path]::GetFullPath($ResolvedHome).TrimEnd('\')
    return @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
            $cl = [string]$_.CommandLine
            if ($cl -notmatch 'irc_agent\.py') { return $false }
            $idx = $cl.IndexOf($watchHome, [StringComparison]::OrdinalIgnoreCase)
            if ($idx -lt 0) { return $false }
            $end = $idx + $watchHome.Length
            if ($end -ge $cl.Length) { return $true }
            return ($cl[$end] -match '[\s\\/"]')
        })
}

function Disconnect-WatchIrc {
    param(
        $State,
        [string]$Reason = 'tui closed'
    )
    $watchHome = [string]$State.ircHome
    if (-not $watchHome) { return }
    $resolved = [IO.Path]::GetFullPath($watchHome)
    if (Test-ForbiddenIrcHome -ResolvedHome $resolved) {
        Write-WatchLog "irc disconnect skipped (forbidden home)"
        return
    }
    if (-not (Test-Path -LiteralPath $resolved)) { return }
    $why = ([string]$Reason).Replace("`r", ' ').Replace("`n", ' ').Trim()
    if (-not $why) { $why = 'tui closed' }
    if ($why.Length -gt 80) { $why = $why.Substring(0, 80) }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText((Join-Path $resolved 'quit.req'), $why, $utf8)
    $epoch = [int][double](Get-Date -UFormat %s)
    $ctrlLine = '{0} {1}' -f $epoch, $why
    [IO.File]::WriteAllText((Join-Path $resolved 'agent.quit.request'), $ctrlLine + [Environment]::NewLine, $utf8)
    $ctrlPy = @(
        'C:\ai\agentic_irc\scripts\agent_control.py',
        'D:\ai\agentic_irc\scripts\agent_control.py',
        (Join-Path $env:USERPROFILE '.grok\skills\agentic-irc\scripts\agent_control.py')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($ctrlPy) {
        $py = (Get-Command python -ErrorAction SilentlyContinue)
        if ($py) {
            Start-Process -FilePath $py.Source -ArgumentList @('-u', $ctrlPy, '--home', $resolved, '--reason', $why, '--request-only') -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
        }
    }
    Write-WatchLog ("irc graceful PART+QUIT requested ({0}) home={1}" -f $why, $resolved)
    $deadline = (Get-Date).AddSeconds(8)
    while ((Get-Date) -lt $deadline) {
        if ((Get-WatchIrcAgentRows -ResolvedHome $resolved).Count -eq 0) { break }
        Start-Sleep -Milliseconds 400
    }
    $left = @(Get-WatchIrcAgentRows -ResolvedHome $resolved)
    foreach ($row in $left) {
        Write-WatchLog ("irc agent still up after QUIT wait pid={0} - stopping" -f $row.ProcessId)
        Stop-Process -Id $row.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $listen = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
            $cl = [string]$_.CommandLine
            $cl -match 'irc_listen\.py' -and $cl -match [regex]::Escape($resolved)
        })
    foreach ($row in $listen) {
        Stop-Process -Id $row.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Get-CursorSeedPrompt {
    param([string]$ResolvedIrcHome)
    return @(
        'Watch seat online. Skills: agent-monitor, watch-seat, agentic-irc + agentic_build (harvest-agent-skills; IRC playbooks to agentic_irc).'
        "IRC home $ResolvedIrcHome - you own irc_agent and irc_listen on this home only. Do not share another seat's listener (that doubles traffic into every connected agent). Monitor tails this home's irc.log and forwards FROM lines into this session."
        'Event-driven: act on monitor payloads; reply on outbox; ping->pong. No UAT.'
    ) -join ' '
}

function Get-AgentPrompt {
    param([string]$ResolvedIrcHome)
    return @(
        'You are a fleet agent on this Windows box (watch seat).'
        'Split: Watch-AgentHealth.ps1 is the deterministic monitor (health, tail irc.log, resume-forward each IRC PRIVMSG into this session). You do not run, restart, or reimplement the monitor.'
        'You are event-driven only off what the monitor forwards (a FROM line) or what Simon types in this IDE turn. Do not idle-wait in chat for the monitor; finish the turn after acting.'
        'Follow skills: agent-monitor + watch-seat (this repo .grok/skills), agentic-irc (join/talk Ergo; no !bobiverse from this seat) and agentic_build. Harvest: harvest-agent-skills for build/fleet; IRC playbooks to SimonBarnett/agentic_irc .grok/skills; AgentMonitor playbooks stay in this repo.'
        "IRC home: $ResolvedIrcHome. You own irc_agent and irc_listen on this home only (one listen per client). Sharing a listener copies every PRIVMSG into every connected agent. Monitor tails this home's irc.log and forwards PRIVMSG; you do not tail IRC in-session."
        'Forbidden homes: ~/.agentic-irc-cursor, cursor-2, bobiverse Watch.'
        'On each wake: treat the payload as the task; reply on outbox if addressed or Simon asked the box; ping -> pong on that target. Then end turn.'
        'Do not stamp UAT. Bob/Simon only. No invented secrets. Do not gut cards or docs.'
    ) -join ' '
}

function Get-GrokRules {
    $skills = Join-Path $env:USERPROFILE '.grok\skills'
    return "Skills live at $skills. Follow agent-monitor, watch-seat, agentic-irc and agentic_build (including harvest-agent-skills). CAST IRON harvest AgentMonitor playbooks to this repo; fleet to agentic_build; IRC to agentic_irc."
}

function Get-DescendantPids {
    param([int]$RootPid)
    $bag = New-Object 'System.Collections.Generic.HashSet[int]'
    if ($RootPid -le 0) { return @() }
    [void]$bag.Add($RootPid)
    $all = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $all) {
            $procId = [int]$row.ProcessId
            $parentId = [int]$row.ParentProcessId
            if ($bag.Contains($parentId) -and -not $bag.Contains($procId)) {
                [void]$bag.Add($procId)
                $changed = $true
            }
        }
    }
    return @($bag)
}

function Test-TreeHealthy {
    param([int]$RootPid)
    if ($RootPid -le 0) { return $false }
    $ids = Get-DescendantPids -RootPid $RootPid
    $alive = @()
    foreach ($id in $ids) {
        $gp = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($gp) { $alive += $gp }
    }
    if ($alive.Count -eq 0) { return $false }
    $stuck = @($alive | Where-Object { $_.Responding -eq $false })
    if ($stuck.Count -gt 0 -and $stuck.Count -eq $alive.Count) { return $false }
    return $true
}

function Stop-WatchedTree {
    param([int]$RootPid)
    if ($RootPid -le 0) { return }
    $ids = Get-DescendantPids -RootPid $RootPid
    foreach ($id in ($ids | Sort-Object -Descending)) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
}

function Test-DropIrcLine {
    param([string]$Line)
    if ($Line -notmatch '^FROM ') { return $true }
    if ($Line -match ' POINT | DIGEST | AGPK | SEAL ') { return $true }
    if ($Line -cmatch ' PING ') { return $true }
    if ($Line -match '(?i)is busy\.|password=|XAI_API_KEY') { return $true }
    return $false
}

function Send-IrcLineToSession {
    param(
        $State,
        [string]$Line
    )
    try {
    if ($State.PSObject.Properties.Name -contains 'lastForwardLine' -and [string]$State.lastForwardLine -eq $Line) {
        return $State
    }
    $trim = $Line.Trim()
    if ($trim -match '^FROM ') {
        if (Test-DropIrcLine -Line $trim) {
            Write-WatchLog ('irc-in (filtered) {0}' -f $trim.Substring(0, [Math]::Min(200, $trim.Length)))
            return $State
        }
        Write-WatchLog ('irc-in {0}' -f $trim.Substring(0, [Math]::Min(350, $trim.Length)))
    }
    elseif ($trim) {
        Write-WatchLog ('listen {0}' -f $trim.Substring(0, [Math]::Min(120, $trim.Length)))
    }
    if (Test-DropIrcLine -Line $Line) { return $State }
    $inbox = Join-Path $script:StateDir 'agent-inbox.txt'
    Add-Content -LiteralPath $inbox -Value $Line -Encoding utf8
    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    $text = $Line.Trim()
    if ($text.Length -gt 350) { $text = $text.Substring(0, 350) }
    $sid = [string]$State.sessionId
    if ($Grok) {
        $exe = Get-GrokAgentPath
        $args = @('--no-auto-update', '--no-alt-screen', '--cwd', $cwdFull, '-r', $sid, '-p', $text)
        Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $cwdFull -WindowStyle Hidden | Out-Null
        $State | Add-Member -NotePropertyName 'lastForwardLine' -NotePropertyValue $Line -Force
        Write-WatchLog ('forward grok session={0} {1}' -f $sid, $text.Substring(0, [Math]::Min(80, $text.Length)))
        return $State
    }
    $agentCmd = Get-CursorAgentCmd
    $fwd = $script:ForwardPromptPath
    if (-not $fwd) { Set-WatchForwardPaths; $fwd = $script:ForwardPromptPath }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($fwd, $text, $utf8)
    $launch = $script:ForwardScriptPath
    $escFwd = $fwd.Replace("'", "''")
    $escCwd = $cwdFull.Replace("'", "''")
    $escAgent = $agentCmd.Replace("'", "''")
    $escSid = $sid.Replace("'", "''")
    if (Test-CursorAgentForwardBusy -SessionId $sid) {
        Write-WatchLog ('forward skipped (agent -p already running session={0})' -f $sid)
        return $State
    }
    $fwdAgent = "& '$escAgent' --trust --force --workspace '$escCwd' -p -- `$prompt"
    $fwdResume = Test-CursorUseResumeCli -State $State
    if ($fwdResume) {
        $fwdAgent = "& '$escAgent' --trust --force --resume '$escSid' --workspace '$escCwd' -p -- `$prompt"
    }
    $body = @(
        '$ErrorActionPreference = ''Stop'''
        "`$prompt = [IO.File]::ReadAllText('$escFwd')"
        "Set-Location -LiteralPath '$escCwd'"
        $fwdAgent
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($launch, $body, $utf8)
    $psExe = (Get-Command powershell.exe).Source
    Start-Process -FilePath $psExe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $launch) -WindowStyle Hidden | Out-Null
    $State | Add-Member -NotePropertyName 'lastForwardLine' -NotePropertyValue $Line -Force
    Write-WatchLog ('forward cursor session={0} {1}' -f $sid, $text.Substring(0, [Math]::Min(80, $text.Length)))
    return $State
    }
    catch {
        Write-WatchLog ("forward failed: $($_.Exception.Message)")
        return $State
    }
}

function Convert-IrcRawLineToFromLine {
    param([string]$Raw)
    $line = $Raw.TrimEnd("`r", "`n").TrimStart([char]0xFEFF)
    if (-not $line) { return $null }
    if ($line -match '^PING ') { return $null }
    if ($line -match '^:\S+ \d{3} ') { return $null }
    if ($line -notmatch '^:(?<nick>[^\s!]+)![^\s]+ PRIVMSG (?<target>\S+) :(?<text>.*)$') { return $null }
    $text = $Matches['text']
    if ($text -match '^(MOOT v1 POINT|BOB DIGEST v1|AGPK v1 |MOOT v1 JOIN)') { return $null }
    if ($text -match '^\x01ACTION lost ') { return $null }
    return ('FROM {0} {1} {2}' -f $Matches['nick'], $Matches['target'], $text)
}

function Initialize-IrcLogTail {
    param($State)
    $watchIrcHome = [string]$State.ircHome
    if (-not $watchIrcHome) { return $State }
    $log = Join-Path $watchIrcHome 'irc.log'
    $hasIrcOffset = $State.PSObject.Properties.Name -contains 'ircLogOffset'
    if (-not $hasIrcOffset) {
        $startAt = 0
        if (Test-Path -LiteralPath $log) {
            $startAt = [int64](Get-Item -LiteralPath $log).Length
        }
        $State | Add-Member -NotePropertyName 'ircLogOffset' -NotePropertyValue $startAt -Force
        Write-WatchLog "irc tail init offset=$startAt (PRIVMSG from irc.log only; ignores listen-tsr)"
    }
    return $State
}

function Sync-IrcForward {
    param($State)
    $watchIrcHome = [string]$State.ircHome
    if (-not $watchIrcHome) { return $State }
    $log = Join-Path $watchIrcHome 'irc.log'
    if (-not (Test-Path -LiteralPath $log)) { return $State }
    $offset = 0
    if ($State.ircLogOffset) { $offset = [int64]$State.ircLogOffset }
    $fs = [IO.File]::Open($log, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        if ($offset -gt $fs.Length) { $offset = 0 }
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [void]$fs.Seek($offset, [IO.SeekOrigin]::Begin)
        while ($fs.Position -lt $fs.Length) {
            $lineStart = $fs.Position
            $lineBytes = New-Object System.Collections.Generic.List[byte]
            $complete = $false
            while ($fs.Position -lt $fs.Length) {
                $b = $fs.ReadByte()
                if ($b -eq 10) {
                    $complete = $true
                    break
                }
                if ($b -eq 13) {
                    if ($fs.Position -lt $fs.Length) {
                        $next = $fs.ReadByte()
                        if ($next -eq 10) {
                            $complete = $true
                            break
                        }
                        [void]$fs.Seek(-1, [IO.SeekOrigin]::Current)
                    }
                    $lineBytes.Add([byte]13)
                    continue
                }
                $lineBytes.Add([byte]$b)
            }
            if (-not $complete) {
                [void]$fs.Seek($lineStart, [IO.SeekOrigin]::Begin)
                break
            }
            $raw = $utf8.GetString($lineBytes.ToArray())
            $from = Convert-IrcRawLineToFromLine -Raw $raw
            if ($from) {
                $State = Send-IrcLineToSession -State $State -Line $from
            }
        }
        $State.ircLogOffset = [int64]$fs.Position
    }
    finally { $fs.Dispose() }
    return $State
}

function Start-CursorInteractiveTui {
    param(
        [string]$AgentCmd,
        [string]$WorkDir,
        [string]$SessionId,
        [string]$PromptPath,
        [switch]$ResumeOnly,
        [switch]$UseResume
    )
    $agentPs1 = Get-CursorAgentPs1
    $utf8 = New-Object System.Text.UTF8Encoding $false
    $launch = Join-Path $script:StateDir 'launch-cursor-tui.ps1'
    $escCwd = $WorkDir.Replace("'", "''")
    $escAgent = $agentPs1.Replace("'", "''")
    $escSid = $SessionId.Replace("'", "''")
    $needsPrompt = $true
    if ($ResumeOnly -and $UseResume) { $needsPrompt = $false }
    if ($ResumeOnly -and -not $UseResume) { $needsPrompt = $false }
    $lines = @(
        '$ErrorActionPreference = ''Stop'''
        "Set-Location -LiteralPath '$escCwd'"
    )
    if ($needsPrompt) {
        $escPrompt = $PromptPath.Replace("'", "''")
        $lines += "`$prompt = [IO.File]::ReadAllText('$escPrompt')"
        if ($UseResume) {
            $lines += "& '$escAgent' --trust --force --resume '$escSid' --workspace '$escCwd' -- `$prompt"
        }
        else {
            $lines += "& '$escAgent' --trust --force --workspace '$escCwd' -- `$prompt"
        }
    }
    else {
        if ($UseResume) {
            $lines += "& '$escAgent' --trust --force --resume '$escSid' --workspace '$escCwd'"
        }
        else {
            $lines += "& '$escAgent' --trust --force --workspace '$escCwd'"
        }
    }
    [IO.File]::WriteAllText($launch, ($lines -join [Environment]::NewLine), $utf8)
    $psExe = (Get-Command powershell.exe).Source
    $started = Start-Process -FilePath $psExe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', $launch
    ) -WorkingDirectory $WorkDir -PassThru -WindowStyle $script:AgentTuiWindowStyle
    $launcherPid = [int]$started.Id
    Start-Sleep -Seconds 8
    $livePid = Resolve-CursorWatchRootPid -SessionId $SessionId -LauncherPid $launcherPid
    if ($livePid -le 0) {
        $why = Get-CursorTuiMissNodeWhy
        Write-WatchLog ("cursor TUI agent pid=$launcherPid but Composer node missing ($why); stopping agent launcher")
        Stop-WatchedTree -RootPid $launcherPid
        return 0
    }
    Write-WatchLog ("cursor TUI started useResume=$UseResume resumeOnly=$ResumeOnly composerPid=$livePid session=$SessionId agentLauncher=$launcherPid")
    return $livePid
}

function Invoke-CursorAgentPrint {
    param(
        [string]$AgentCmd,
        [string]$WorkDir,
        [string]$SessionId,
        [string]$PromptText,
        [string]$LogTag,
        [switch]$UseResume
    )
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $promptFile = Join-Path $script:StateDir 'cursor-print.prompt.txt'
    $outLog = Join-Path $script:StateDir 'cursor-print.log'
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($promptFile, $PromptText, $utf8)
    $launch = Join-Path $script:StateDir 'cursor-print.ps1'
    $escPrompt = $promptFile.Replace("'", "''")
    $escCwd = $WorkDir.Replace("'", "''")
    $escAgent = $AgentCmd.Replace("'", "''")
    $escSid = $SessionId.Replace("'", "''")
    $escOut = $outLog.Replace("'", "''")
    $agentLine = "& '$escAgent' --trust --force --workspace '$escCwd' -p -- `$prompt *>> '$escOut'"
    if ($UseResume) {
        $agentLine = "& '$escAgent' --trust --force --resume '$escSid' --workspace '$escCwd' -p -- `$prompt *>> '$escOut'"
    }
    $lines = @(
        '$ErrorActionPreference = ''Stop'''
        "`$prompt = [IO.File]::ReadAllText('$escPrompt')"
        "Set-Location -LiteralPath '$escCwd'"
        $agentLine
        'exit $LASTEXITCODE'
    )
    [IO.File]::WriteAllText($launch, ($lines -join [Environment]::NewLine), $utf8)
    $psExe = (Get-Command powershell.exe).Source
    $proc = Start-Process -FilePath $psExe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', $launch
    ) -WorkingDirectory $WorkDir -PassThru -WindowStyle Hidden -Wait
    $code = if ($null -ne $proc.ExitCode) { [int]$proc.ExitCode } else { -1 }
    Write-WatchLog ("cursor {0} -p exit={1} session={2} log={3}" -f $LogTag, $code, $SessionId, $outLog)
    if ($code -ne 0 -and (Test-Path -LiteralPath $outLog)) {
        $tail = Get-Content -LiteralPath $outLog -Tail 3 -ErrorAction SilentlyContinue
        foreach ($ln in $tail) { Write-WatchLog ("cursor-print: {0}" -f $ln) }
    }
    return $code
}

function Start-WatchedAgent {
    param($State)
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $promptFile = Join-Path $script:StateDir 'prompt.txt'
    $resolvedHome = [string]$State.ircHome
    $prompt = Get-AgentPrompt -ResolvedIrcHome $resolvedHome
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($promptFile, $prompt, $utf8)

    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    if (-not (Test-Path -LiteralPath $cwdFull)) {
        throw "Cwd not found: $cwdFull (pass -Cwd or ensure D:\ai etc. exists)"
    }

    $resume = [bool]$State.seenSession
    if ($Cursor -and -not $resume) {
        $chatDone = ($State.PSObject.Properties.Name -contains 'cursorChatCreated') -and [bool]$State.cursorChatCreated
        if (-not $chatDone) {
            $head = Get-CommitHeadroomGb
            if ($head.FreeGb -ge 0 -and $head.FreeGb -lt 0.75) {
                Write-WatchLog "low commit before create-chat ($($head.FreeGb) GB free) - pruning orphan watch forwards only"
                Stop-OrphanCursorWatchForwards | Out-Null
                Start-Sleep -Seconds 2
            }
            $agentCmdForChat = Get-CursorAgentCmd
            $chat = New-CursorChatSessionId -AgentCmd $agentCmdForChat -WorkDir $cwdFull
            $State.sessionId = [string]$chat.SessionId
            $State | Add-Member -NotePropertyName 'cursorSessionValid' -NotePropertyValue ([bool]$chat.ServerChat) -Force
            $State | Add-Member -NotePropertyName 'cursorChatCreated' -NotePropertyValue $true -Force
            Write-WatchLog "cursor new session id=$($State.sessionId) serverChat=$([bool]$chat.ServerChat)"
        }
    }
    elseif (-not $State.sessionId) {
        $State.sessionId = [guid]::NewGuid().ToString()
    }

    if ($Cursor) {
        $agentCmd = Get-CursorAgentCmd
        if (Test-CursorPrintOnlyMode -State $State) {
            $State.rootPid = 0
            return [pscustomobject]@{ Kind = 'cursor'; Exe = $agentCmd; Process = $null; RootPid = 0; State = $State }
        }
        $sid = [string]$State.sessionId
        $useResumeTui = Test-CursorUseResumeForTui -State $State -ResumeShortcut:$resume
        $livePid = Resolve-CursorWatchRootPid -SessionId $sid -LauncherPid 0
        if ($livePid -le 0) {
            $tuiPromptPath = $promptFile
            if (-not $resume) {
                $seedFile = Join-Path $script:StateDir 'cursor-tui-seed.prompt.txt'
                [IO.File]::WriteAllText($seedFile, (Get-CursorSeedPrompt -ResolvedIrcHome $resolvedHome), $utf8)
                $tuiPromptPath = $seedFile
                Write-WatchLog "cursor New: spawning Composer TUI window=$($script:AgentTuiWindowStyle) (short seed); IRC forwards stay hidden agent -p"
            }
            else {
                Write-WatchLog "cursor Resume: spawning Composer TUI window=$($script:AgentTuiWindowStyle) (resume attach)"
            }
            $head = Get-CommitHeadroomGb
            $refusedLowCommit = $false
            if ($head.FreeGb -ge 0 -and $head.FreeGb -lt 0.5) {
                Write-CursorAgentProcessSnapshot -Reason 'refusing TUI spawn (need ~0.5GB+ free commit)'
                $livePid = 0
                $refusedLowCommit = $true
            }
            else {
                $livePid = Start-CursorInteractiveTui -AgentCmd $agentCmd -WorkDir $cwdFull -SessionId $sid -PromptPath $tuiPromptPath -ResumeOnly:$resume -UseResume:$useResumeTui
            }
            if ($livePid -gt 0) {
                $State = Sync-CursorSessionFromComposer -State $State -ComposerPid $livePid
                $State.seenSession = $true
            }
            else {
                if (-not $refusedLowCommit) {
                    $why = Get-CursorTuiMissNodeWhy
                    Write-CursorAgentProcessSnapshot -Reason "cursor Composer not running ($why)"
                }
                $State = Set-CursorPrintOnlyMode -State $State -Enable
            }
        }
        else {
            Write-WatchLog "cursor TUI already live pid=$livePid session=$sid"
            $State.seenSession = $true
        }
        $State.rootPid = $livePid
        return [pscustomobject]@{ Kind = 'cursor'; Exe = $agentCmd; Process = $null; RootPid = $livePid; State = $State }
    }

    if ($Grok) {
        $exe = Get-GrokAgentPath
        $argList = @('--no-auto-update', '--no-alt-screen', '--cwd', $cwdFull)
        if ($resume) {
            $argList += @('-r', [string]$State.sessionId)
        }
        else {
            $argList += @('-s', [string]$State.sessionId, '--rules', (Get-GrokRules))
        }
        $argList += $prompt
        $started = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $cwdFull -PassThru -WindowStyle $script:AgentTuiWindowStyle
        $State.seenSession = $true
        $State.rootPid = [int]$started.Id
        return [pscustomobject]@{ Kind = 'grok'; Exe = $exe; Process = $started; RootPid = [int]$started.Id; State = $State }
    }

}

function Start-DetachedWatchWorkerIfNeeded {
    if ($WatchWorker) { return }
    $sp = $PSCommandPath
    if (-not $sp) { throw 'PSCommandPath missing; run via -File.' }
    $workerArgs = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-WindowStyle', 'Hidden',
        '-File', $sp,
        '-WatchWorker',
        '-Windows', 'off'
    )
    if ($Grok) { $workerArgs += '-Grok' }
    if ($Cursor) { $workerArgs += '-Cursor' }
    if ($New) { $workerArgs += '-New' }
    if ($PSBoundParameters.ContainsKey('Cwd')) { $workerArgs += @('-Cwd', $Cwd) }
    $workerArgs += @('-IrcHome', $IrcHome)
    if ($PSBoundParameters.ContainsKey('PollSeconds')) { $workerArgs += @('-PollSeconds', [string]$PollSeconds) }
    if ($PSBoundParameters.ContainsKey('CrashBackoffSeconds')) { $workerArgs += @('-CrashBackoffSeconds', [string]$CrashBackoffSeconds) }
    $log = $script:LogFile
    if (-not $log) { $log = $LogPath }
    if (-not $log) {
        $log = Join-Path $env:USERPROFILE 'Desktop\Watch-AgentHealth\Watch-AgentHealth.log'
    }
    $workerArgs += @('-LogPath', $log)
    New-Item -ItemType File -Force -Path $log | Out-Null
    $proc = Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList $workerArgs -WindowStyle Hidden -PassThru
    $boot = '{0:o} hidden watch monitor pid={1} (-Windows off; log={2})' -f [datetime]::UtcNow, $proc.Id, $log
    Add-Content -LiteralPath $log -Value $boot -Encoding utf8
    Write-Host $boot
    exit 0
}

function Register-WatchWorkerProcess {
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $self = $PID
    $kindFlag = if ($Cursor) { '-Cursor' } else { '-Grok' }
    $rows = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue)
    foreach ($row in $rows) {
        $opid = [int]$row.ProcessId
        if ($opid -eq $self) { continue }
        $cl = [string]$row.CommandLine
        if ($cl -notmatch 'Watch-AgentHealth\.ps1') { continue }
        if ($cl -notmatch '-WatchWorker') { continue }
        if ($cl -notmatch [regex]::Escape($kindFlag)) { continue }
        Write-WatchLog "keeping live watch worker pid=$opid (multiple clients; not replacing)"
    }
    Set-Content -LiteralPath $script:WorkerPidPath -Value ([string]$self) -Encoding ascii -NoNewline
    Write-WatchLog "watch worker online pid=$self kind=$($script:KindName) slot=$($script:ClientSlot) ircHome=$IrcHome"
}

function Unregister-WatchWorkerProcess {
    if (-not (Test-Path -LiteralPath $script:WorkerPidPath)) { return }
    try {
        $onDisk = [int](Get-Content -LiteralPath $script:WorkerPidPath -Raw)
        if ($onDisk -eq $PID) {
            Remove-Item -LiteralPath $script:WorkerPidPath -Force -ErrorAction SilentlyContinue
        }
    }
    catch { }
}

$boundSlot = Bind-WatchClientSlot
if ($boundSlot) {
    $script:ClientSlot = [int]$boundSlot.Slot
    $script:StatePath = [string]$boundSlot.StatePath
    $script:WorkerPidPath = [string]$boundSlot.WorkerPidPath
    $IrcHome = [string]$boundSlot.IrcHome
}
else {
    $script:ClientSlot = Resolve-WatchSlotFromIrcHome -WatchHomePath $IrcHome
    $boundPaths = Get-WatchSlotPaths -Slot $script:ClientSlot
    $script:StatePath = [string]$boundPaths.StatePath
    $script:WorkerPidPath = [string]$boundPaths.WorkerPidPath
}
Set-WatchForwardPaths

$script:LogFile = $LogPath
if (-not $script:LogFile) {
    $logLeaf = if ($script:ClientSlot -le 1) { 'Watch-AgentHealth.log' } else { 'Watch-AgentHealth-{0}.log' -f $script:ClientSlot }
    $script:LogFile = Join-Path $env:USERPROFILE ('Desktop\Watch-AgentHealth\{0}' -f $logLeaf)
}

New-Item -ItemType File -Force -Path $script:LogFile | Out-Null
if (-not $WatchWorker -and $Windows -eq 'on') {
    $WatchWorker = $true
}
Start-DetachedWatchWorkerIfNeeded
$state = Read-WatchState
if (-not $state) {
    $state = [pscustomobject]@{
        kind         = $script:KindName
        sessionId    = [guid]::NewGuid().ToString()
        seenSession  = $false
        ircHome      = $IrcHome
        ircLogOffset = 0
        rootPid      = 0
    }
}
if ($New) {
    $oldWatchSid = [string]$state.sessionId
    $state = Reset-WatchSessionForNew -State $state
    $state.kind = $script:KindName
    Write-WatchState -Obj $state
    Write-WatchLog "session reset (--new) session=$($state.sessionId)"
    if ($Cursor) {
        $n = 0
        if ($oldWatchSid) {
            $n += Stop-CursorAgentNodesForSession -SessionId $oldWatchSid
        }
        $n += Stop-OrphanCursorWatchForwards
        if ($n -gt 0) {
            Write-WatchLog "cursor --new pruned $n watch leftover node(s)"
            Start-Sleep -Seconds 2
        }
    }
}

$state = Initialize-WatchIrcHome -State $state
if ($WatchWorker) {
    Register-WatchWorkerProcess
}
$state = Initialize-IrcLogTail -State $state
Write-WatchLog "watch start kind=$($script:KindName) slot=$($script:ClientSlot) windows=$Windows cwd=$Cwd session=$($state.sessionId) ircHome=$($state.ircHome) (tails irc.log; irc-in lines echo here)"

$current = $null
try {
    Write-WatchState -Obj $state

    $script:LeaveWatch = $false
    while ($true) {
        try {
        $needStart = $false
        if ($script:LeaveWatch) {
            break
        }
        if (-not $current) {
            $needStart = $true
        }
        elseif ($Cursor) {
            if (Test-CursorPrintOnlyMode -State $state) {
                $current.RootPid = 0
                $state.rootPid = 0
            }
            else {
                $livePid = Resolve-CursorWatchRootPid -SessionId ([string]$state.sessionId) -LauncherPid $current.RootPid
                if ($livePid -le 0) {
                    Write-WatchLog "cursor Composer not running session=$($state.sessionId) - QUIT this slot; start a new client (do not restart this seat)"
                    Disconnect-WatchIrc -State $state -Reason 'tui closed'
                    if ($current.RootPid -gt 0) {
                        Stop-WatchedTree -RootPid $current.RootPid
                    }
                    $state = Set-CursorPrintOnlyMode -State $state -Enable
                    $current.RootPid = 0
                    $script:LeaveWatch = $true
                    break
                }
                else {
                    if ($livePid -ne $current.RootPid) {
                        $current.RootPid = $livePid
                        $state.rootPid = $livePid
                    }
                    $state = Sync-CursorSessionFromComposer -State $state -ComposerPid $livePid
                }
            }
        }
        elseif (-not (Test-TreeHealthy -RootPid $current.RootPid)) {
            Write-WatchLog "unhealthy agent tree rootPid=$($current.RootPid) - QUIT IRC; start a new client (do not restart this seat)"
            Disconnect-WatchIrc -State $state -Reason 'tui closed'
            Stop-WatchedTree -RootPid $current.RootPid
            $current.RootPid = 0
            $script:LeaveWatch = $true
            break
        }

        if ($needStart) {
            $firstRun = -not [bool]$state.seenSession
            $started = Start-WatchedAgent -State $state
            $current = $started
            $state = $started.State
            $state.rootPid = $started.RootPid
            Write-WatchState -Obj $state
            if ($Cursor -and $started.RootPid -le 0) {
                $noTui = if ($Windows -eq 'on') { ' (no live Composer TUI; windows=on)' } else { '' }
                Write-WatchLog "cursor composer not live$noTui session=$($state.sessionId) firstRun=$firstRun exe=$($started.Exe)"
            }
            else {
                Write-WatchLog "started kind=$($started.Kind) exe=$($started.Exe) rootPid=$($started.RootPid) session=$($state.sessionId) firstRun=$firstRun"
                if ($Cursor -and $started.RootPid -gt 0) {
                    Write-WatchLog "cursor seat: Composer TUI window=$($script:AgentTuiWindowStyle); IRC wakes use hidden agent -p"
                }
            }
        }

        $state = Sync-IrcForward -State $state
        Write-WatchState -Obj $state
        Start-Sleep -Seconds $PollSeconds
        }
        catch {
            Write-WatchLog ("watch loop error: $($_.Exception.Message)")
            Start-Sleep -Seconds $CrashBackoffSeconds
        }
    }
}
catch {
    Write-WatchLog ("watch fatal: $($_.Exception.Message)")
}
finally {
    if ($state) {
        Disconnect-WatchIrc -State $state -Reason 'watch stop'
    }
    if ($WatchWorker) {
        Unregister-WatchWorkerProcess
    }
    if ($current) {
        Write-WatchLog "watch stop - leaving process tree rootPid=$($current.RootPid) session=$($state.sessionId)"
    }
    elseif ($WatchWorker) {
        Write-WatchLog "watch stop worker pid=$PID session=$($state.sessionId)"
    }
}
