<#
.SYNOPSIS
  Start a free-nick #bobiverse listen home for bob_git_hook announce verification (FR #88).

.DESCRIPTION
  ircBob holds Bob-<machine> / NickServ bob-<machine>. A second client that tries
  bob-<machine> without that SASL gets NICKNAME_RESERVED and never joins, so
  ~/.agentic-irc-bobiverse/irc.log cannot see Jeeves GIT lines.

  This helper starts irc_agent.py as gitannounce-<machine> into a dedicated home
  (~/.agentic-irc-gitannounce) with server PASS only (no ear NickServ). Then:

    python tools/bob_git_hook.py SimonBarnett/<name> --irc-log $env:USERPROFILE\.agentic-irc-gitannounce\irc.log

  Does not weaken the announce gate. Does not touch Ergo or BobIrcd.
#>
[CmdletBinding()]
param(
    [string]$MachineId = '',
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Channel = '#bobiverse',
    [string]$IrcAgent = '',
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
if (-not $MachineId) {
    if ($env:BOB_MACHINE_ID) { $MachineId = $env:BOB_MACHINE_ID.Trim() }
    else { $MachineId = $env:COMPUTERNAME.ToLowerInvariant() }
}
$MachineId = ($MachineId -replace '[^a-zA-Z0-9-]', '').ToLowerInvariant()
if (-not $MachineId) { throw 'MachineId empty' }

$nick = "gitannounce-$MachineId"
$listenHome = Join-Path $env:USERPROFILE '.agentic-irc-gitannounce'
New-Item -ItemType Directory -Force -Path $listenHome | Out-Null

$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (-not (Test-Path -LiteralPath $pwFile)) {
    throw "missing $pwFile (Ergo connect PASS for guests)"
}

if (-not $Python) {
    foreach ($c in @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
        )) {
        if (Test-Path -LiteralPath $c) { $Python = $c; break }
    }
}
if (-not $Python) {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) { throw 'python.exe not found' }

if (-not $IrcAgent) {
    $candidates = New-Object System.Collections.Generic.List[string]
    [void]$candidates.Add('C:\ai\bob\scripts\irc_agent.py')
    [void]$candidates.Add('D:\ai\agentic_irc\scripts\irc_agent.py')
    if ($PSScriptRoot) {
        [void]$candidates.Add((Join-Path $PSScriptRoot '..\..\..\..\common\scripts\irc_agent.py'))
        [void]$candidates.Add((Join-Path $PSScriptRoot '..\..\..\scripts\irc_agent.py'))
    }
    if ($env:BOB_INSTALL_ROOT -and $env:BOB_INSTALL_ROOT.Trim()) {
        [void]$candidates.Add((Join-Path $env:BOB_INSTALL_ROOT.Trim() 'scripts\irc_agent.py'))
        [void]$candidates.Add((Join-Path $env:BOB_INSTALL_ROOT.Trim() 'bob\scripts\irc_agent.py'))
        [void]$candidates.Add((Join-Path $env:BOB_INSTALL_ROOT.Trim() 'common\scripts\irc_agent.py'))
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { $IrcAgent = $c; break }
    }
}
if (-not $IrcAgent -or -not (Test-Path -LiteralPath $IrcAgent)) {
    throw 'irc_agent.py not found (set -IrcAgent)'
}

# Drop ear NickServ from this home so we do not attempt bob-* SASL.
$ns = Join-Path $listenHome 'nickserv.password'
if (Test-Path -LiteralPath $ns) {
    Rename-Item -LiteralPath $ns -NewName ('nickserv.password.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) -Force
}

$pass = (Get-Content -LiteralPath $pwFile -Raw).Trim()
# bobiverse irc_agent reads BOB_IRC_PASSWORD; agentic_irc reads AGENTIC_IRC_PASSWORD
$env:AGENTIC_IRC_PASSWORD = $pass
$env:BOB_IRC_PASSWORD = $pass
$env:AGENTIC_IRC_HOME = $listenHome
$env:BOB_HOME = $listenHome
$env:AGENTIC_IRC_DEBUG = '1'
$env:BOB_IRC_DEBUG = '1'
# Leave AGENTIC_IRC_RECONNECT_MAX unset for a standing listen (tests may set it).

$work = Split-Path -Parent $IrcAgent
$proc = Start-Process -FilePath $Python -ArgumentList @(
    '-u', $IrcAgent,
    '--host', $IrcHost,
    '--port', "$Port",
    '--nick', $nick,
    '--channel', $Channel,
    '--home', $listenHome
) -WorkingDirectory $work -WindowStyle Hidden -PassThru
# do not print $pass

$log = Join-Path $listenHome 'irc.log'
Write-Host "OK started git-announce listen pid=$($proc.Id) nick=$nick home=$listenHome"
Write-Host "Wait for JOIN, then: python tools/bob_git_hook.py SimonBarnett/<name> --irc-log $log"
return [pscustomobject]@{ Pid = $proc.Id; Nick = $nick; Home = $listenHome; IrcLog = $log }
