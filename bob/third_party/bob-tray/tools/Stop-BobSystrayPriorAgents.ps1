#Requires -Version 5.1
# CAST IRON (Simon 2026-09-27): Start/Restart Bob Systray MUST close prior agent
# sessions (Watch-AgentHealth seats, grok.exe TUI, cursor-agent). Fleet watchers stay.
# ASCII-only for Windows PowerShell 5.1. Never print secrets.
[CmdletBinding()]
param(
    [switch]$WhatIf
)

$ErrorActionPreference = 'Continue'

$keep = [System.Collections.Generic.HashSet[int]]::new()
$p = $PID
while ($p -and $p -gt 0) {
    [void]$keep.Add([int]$p)
    $p = (Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue).ParentProcessId
}

# Never kill fleet infrastructure from this script.
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
function Add-KeepByMatch {
    param([string]$Pattern, [int]$MaxKeep = 8)
    $hits = @($all | Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern } |
        Sort-Object CreationDate -Descending)
    $n = 0
    foreach ($h in $hits) {
        if ($n -ge $MaxKeep) { break }
        [void]$keep.Add([int]$h.ProcessId)
        $n++
    }
}
Add-KeepByMatch 'Watch-BobTray|_Watch-BobTray-' 2
Add-KeepByMatch 'Watch-BobJobs' 1
Add-KeepByMatch '_Watch-Bobiverse|Watch-Bobiverse' 1
Add-KeepByMatch '_Watch-IrcTsr|Watch-IrcTsr|Irc-Tsr-Runner' 4
Add-KeepByMatch 'Watch-GrokTalk|_Watch-GrokTalk' 1
Add-KeepByMatch 'nick bob-|bob-ionos|bob-flamingo|bob-marchhare|bob-ce-priority' 4
Add-KeepByMatch 'nick Jeeves|--chair' 1
Add-KeepByMatch 'bobcallback\.py' 1
Add-KeepByMatch 'Start-MediaHost' 1
Add-KeepByMatch 'ms-vscode\.powershell|Microsoft VS Code|shellIntegration' 4

function Test-BobPriorAgentProcess {
    param($Pr)
    if (-not $Pr) { return $false }
    $name = ([string]$Pr.Name).ToLowerInvariant()
    $cmd = if ($Pr.CommandLine) { [string]$Pr.CommandLine } else { '' }
    # Agent TUIs / CLIs (screenshot: Grok "New Agent" window must die on Restart)
    if ($name -eq 'grok.exe') { return $true }
    # Grok Bot desktop: kill top-level only (no --type=); children die with parent.
    if ($name -eq 'grok bot.exe' -and $cmd -notmatch '--type=') { return $true }
    if ($name -eq 'cursor-agent.exe') { return $true }
    if ($name -eq 'agent.exe' -and $cmd -match '(?i)cursor') { return $true }
    # Watch seats (PowerShell host for AgentMonitor)
    if ($cmd -match 'Watch-AgentHealth') { return $true }
    if ($cmd -match '-WatchWorker') { return $true }
    if ($cmd -match '(?i)[\\/]agentic-irc-watch-(grok|cursor)') { return $true }
    # Cursor agent launcher scripts
    if ($cmd -match '(?i)cursor-agent(\.ps1|\.cmd|\.exe)') { return $true }
    if ($cmd -match '(?i)\\.cursor\\.*\\agent(\.exe|\.cmd)') { return $true }
    return $false
}

$targets = @($all | Where-Object {
        -not $keep.Contains([int]$_.ProcessId) -and (Test-BobPriorAgentProcess $_)
    })

$killed = New-Object System.Collections.Generic.List[object]
foreach ($pr in $targets) {
    $id = [int]$pr.ProcessId
    $cmd = if ($pr.CommandLine) { [string]$pr.CommandLine } else { '(none)' }
    $short = if ($cmd.Length -gt 140) { $cmd.Substring(0, 140) + '...' } else { $cmd }
    if ($WhatIf) {
        $killed.Add([pscustomobject]@{ Pid = $id; Name = $pr.Name; Cmd = $short })
        continue
    }
    try {
        Stop-Process -Id $id -Force -ErrorAction Stop
        $killed.Add([pscustomobject]@{ Pid = $id; Name = $pr.Name; Cmd = $short })
    }
    catch {
        $killed.Add([pscustomobject]@{ Pid = $id; Name = $pr.Name; Cmd = ('FAIL: ' + $_.Exception.Message) })
    }
}

# Second pass: children of killed parents (node/python under agent hosts)
Start-Sleep -Milliseconds 400
if (-not $WhatIf -and $killed.Count -gt 0) {
    $killedIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($k in $killed) { if ($k.Pid) { [void]$killedIds.Add([int]$k.Pid) } }
    $again = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ParentProcessId -and $killedIds.Contains([int]$_.ParentProcessId) -and
            $_.Name -match '^(node|python|pythonw|powershell|pwsh|grok)\.exe$'
        })
    foreach ($pr in $again) {
        if ($keep.Contains([int]$pr.ProcessId)) { continue }
        try {
            Stop-Process -Id ([int]$pr.ProcessId) -Force -ErrorAction Stop
            $cmd = if ($pr.CommandLine) { [string]$pr.CommandLine } else { '(none)' }
            $short = if ($cmd.Length -gt 140) { $cmd.Substring(0, 140) + '...' } else { $cmd }
            $killed.Add([pscustomobject]@{ Pid = [int]$pr.ProcessId; Name = $pr.Name; Cmd = ('child: ' + $short) })
        }
        catch { }
    }
}

Write-Output ("PRIOR_AGENTS_KILLED={0}" -f $killed.Count)
$killed | Format-Table -AutoSize | Out-String -Width 200 | Write-Output

[pscustomobject]@{
    ok     = $true
    killed = $killed.Count
    whatIf = [bool]$WhatIf
} | ConvertTo-Json -Compress
exit 0
