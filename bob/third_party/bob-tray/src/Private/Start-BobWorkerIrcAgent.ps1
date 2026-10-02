function Test-BobLiveIrcSpawnAllowed {
    <#
    .SYNOPSIS
      FR #329: Test-Pack and other offline runs must not join live fleet Ergo.
    #>
    [CmdletBinding()]
    param(
        [string]$HostName = '',
        [string]$HomePath = ''
    )
    $flag = ([string]$env:BOB_TEST_NO_LIVE_IRC).Trim().ToLowerInvariant()
    if ($flag -in @('1', 'true', 'yes')) {
        return [pscustomobject]@{ Allowed = $false; Reason = 'BOB_TEST_NO_LIVE_IRC' }
    }
    $h = ([string]$HostName).Trim().ToLowerInvariant()
    if (-not $h) { $h = ([string]$env:AGENTIC_IRC_HOST).Trim().ToLowerInvariant() }
    if (-not $h) { $h = 'irc.ntsa.uk' }
    if ($h -eq 'irc.ntsa.uk' -or $h -eq 'irc.libera.chat') {
        $agentHomePath = ([string]$HomePath).Trim()
        if (-not $agentHomePath) { $agentHomePath = ([string]$env:BOB_IRC_HOME).Trim() }
        if (-not $agentHomePath) { $agentHomePath = ([string]$env:AGENTIC_IRC_HOME).Trim() }
        if ($agentHomePath -match '(?i)[\\/]bob-bridge-test-') {
            return [pscustomobject]@{ Allowed = $false; Reason = 'bob-bridge-test-home' }
        }
    }
    return [pscustomobject]@{ Allowed = $true; Reason = '' }
}

function Get-BobBridgeTestIrcAgentRows {
    param([object[]]$Processes)
    $temp = [IO.Path]::GetTempPath().TrimEnd('\', '/')
    $needle = 'bob-bridge-test-'
    $out = @()
    foreach ($p in @($Processes)) {
        $cl = [string]$p.CommandLine
        if (-not $cl) { continue }
        if ($cl -notmatch 'irc_agent\.py') { continue }
        if ($cl -notmatch [regex]::Escape($needle)) { continue }
        if ($cl -notmatch '(?i)[\\/]Temp[\\/]bob-bridge-test-' -and $cl -notmatch [regex]::Escape($temp)) {
            # still allow if path contains bob-bridge-test- under any temp-like folder
            if ($cl -notmatch '(?i)bob-bridge-test-') { continue }
        }
        $out += $p
    }
    return $out
}

function Stop-BobBridgeTestIrcOrphans {
    [CmdletBinding()]
    param(
        [object[]]$Processes,
        [scriptblock]$StopFn,
        [switch]$RequireDeadParent
    )
    if ($null -eq $Processes) {
        $Processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine })
    }
    $killed = @()
    foreach ($row in @(Get-BobBridgeTestIrcAgentRows -Processes $Processes)) {
        $procId = [int]$row.ProcessId
        if ($RequireDeadParent) {
            $pp = 0
            try { $pp = [int]$row.ParentProcessId } catch { $pp = 0 }
            if ($pp -gt 0 -and (Get-Process -Id $pp -ErrorAction SilentlyContinue)) {
                continue
            }
        }
        if ($StopFn) { & $StopFn $procId }
        else { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
        $killed += $procId
    }
    return $killed
}

function Start-BobWorkerIrcAgent {
    <#
    .SYNOPSIS
      Spawn shop-only worker irc_agent (agentic_irc #70 MUST 2).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][int]$WorkerPid,
        [string]$MachineId = $(Get-ThisMachineId)
    )
    if (-not $MachineId) { $MachineId = $env:COMPUTERNAME.ToLowerInvariant() }
    if ($WorkerPid -le 0) { return }
    $gate = Test-BobLiveIrcSpawnAllowed
    if (-not $gate.Allowed) {
        Write-Verbose ("Start-BobWorkerIrcAgent refused ({0})" -f $gate.Reason)
        return
    }
    $spawn = $null
    foreach ($root in @('C:\ai\agentic_irc', 'D:\ai\agentic_irc')) {
        $cand = Join-Path $root 'scripts\start_worker_irc_agent.py'
        if (Test-Path -LiteralPath $cand) { $spawn = $cand; break }
    }
    if (-not $spawn) { return }
    $py = $null
    foreach ($c in @(
            (Get-Command python.exe -ErrorAction SilentlyContinue).Source,
            'C:\Python312\python.exe',
            'C:\Python311\python.exe',
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { $py = $c; break }
    }
    if (-not $py) { return }
    try {
        Start-Process -FilePath $py -ArgumentList @(
            '-u', $spawn,
            '--machine-id', $MachineId,
            '--pid', "$WorkerPid"
        ) -WindowStyle Hidden | Out-Null
    }
    catch { }
}
