# Cleanup-OrphanAgents.ps1 - close orphan python/node/powershell; keep fleet.
# Skill: cleanup-orphans. Never print secrets.
# ASCII-only. Do not use SupportsShouldProcess here: it already defines -WhatIf
# and an explicit [switch]$WhatIf duplicates the parameter (breaks Start-BobFleetTray tidy).
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

$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^(powershell|pwsh|python|pythonw|node)\.exe$'
    })

function Add-KeepByMatch {
    param([string]$Pattern, [int]$MaxKeep = 1)
    $hits = @($procs | Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern } |
        Sort-Object CreationDate -Descending)
    $n = 0
    foreach ($h in $hits) {
        if ($n -ge $MaxKeep) { break }
        [void]$keep.Add([int]$h.ProcessId)
        $n++
    }
}

Add-KeepByMatch 'Watch-BobTray' 1
Add-KeepByMatch 'Watch-BobJobs' 1
Add-KeepByMatch '_Watch-Bobiverse|Watch-Bobiverse' 1
Add-KeepByMatch '_Watch-IrcTsr|Watch-IrcTsr' 1
Add-KeepByMatch 'Watch-GrokTalk|_Watch-GrokTalk' 1
Add-KeepByMatch 'Start-MediaHost' 1
Add-KeepByMatch 'nick bob-|bob-ionos|bob-flamingo|bob-marchhare|bob-ce-priority' 2
Add-KeepByMatch 'nick Jeeves|--chair' 1
Add-KeepByMatch 'bobcallback\.py' 1
Add-KeepByMatch 'Irc-Tsr-Runner\.ps1.*\.agentic-irc-cursor($|["''\s-])' 2
Add-KeepByMatch 'irc_listen\.py --home .*\.agentic-irc-cursor($|["''\s])' 1
# Live AgentMonitor watch seats (do not kill during systray tidy)
Add-KeepByMatch 'agentic-irc-watch-(grok|cursor)' 6
Add-KeepByMatch 'Watch-AgentHealth' 4
Add-KeepByMatch 'xero-mcp-server' 2
Add-KeepByMatch 'cursor-agent\.ps1' 2
Add-KeepByMatch 'ms-vscode\.powershell|Microsoft VS Code|shellIntegration' 4

$changed = $true
while ($changed) {
    $changed = $false
    foreach ($pr in $procs) {
        $id = [int]$pr.ProcessId
        $pp = [int]$pr.ParentProcessId
        if (-not $keep.Contains($pp) -or $keep.Contains($id)) { continue }
        $parent = $procs | Where-Object { $_.ProcessId -eq $pp } | Select-Object -First 1
        $pcmd = if ($parent) { [string]$parent.CommandLine } else { '' }
        if ($pcmd -match 'Irc-Tsr|Watch-Bob|Watch-Irc|Watch-Grok|bob-ionos|bob-flamingo|Jeeves|bobcallback|cursor-agent|xero-mcp|MediaHost') {
            [void]$keep.Add($id)
            $changed = $true
        }
    }
}

$killed = New-Object System.Collections.Generic.List[object]
foreach ($pr in $procs) {
    $id = [int]$pr.ProcessId
    if ($keep.Contains($id)) { continue }
    $cmd = if ($pr.CommandLine) { [string]$pr.CommandLine } else { '(none)' }
    $short = if ($cmd.Length -gt 120) { $cmd.Substring(0, 120) + '...' } else { $cmd }
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

Write-Output "KEPT=$($keep.Count) KILLED=$($killed.Count)"
$killed | Format-Table -AutoSize | Out-String -Width 200 | Write-Output

Start-Sleep -Seconds 1
$left = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^(powershell|pwsh|python|pythonw|node)\.exe$'
    })
Write-Output "REMAINING=$($left.Count)"
$left | ForEach-Object {
    $c = if ($_.CommandLine) { [string]$_.CommandLine } else { '(none)' }
    if ($c.Length -gt 140) { $c = $c.Substring(0, 140) + '...' }
    '{0,6} {1,-14} {2}' -f $_.ProcessId, $_.Name, $c
}

$tray = @($left | Where-Object { $_.CommandLine -and $_.CommandLine -match 'Watch-BobTray' })
if ($tray.Count -ne 1) {
    Write-Warning "Watch-BobTray count=$($tray.Count) — recycle tray (skill bob-fleet-tray / Reinstall-AgentSkills -RecycleTray)"
}

[pscustomobject]@{
    ok       = $true
    kept     = $keep.Count
    killed   = $killed.Count
    remaining = $left.Count
    tray     = $tray.Count
}
