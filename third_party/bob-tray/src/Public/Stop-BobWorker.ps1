function Stop-BobWorker {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SessionId
    )
    $overlay = Read-Overlay
    $entry = @($overlay.workers | Where-Object { $_.sessionId -eq $SessionId }) | Select-Object -First 1
    $overlay.workers = @($overlay.workers | Where-Object { $_.sessionId -ne $SessionId })
    Write-Overlay $overlay

    $dir = Get-WorkerDir $SessionId
    $statusPath = Join-Path $dir 'status.json'
    $status = Read-JsonFile $statusPath
    $agent = $null
    if ($entry -and $entry.PSObject.Properties.Name -contains 'agent' -and $entry.agent) {
        $agent = [string]$entry.agent
    }
    elseif ($status -and $status.PSObject.Properties.Name -contains 'agent' -and $status.agent) {
        $agent = [string]$status.agent
    }
    if ($agent -and (Test-GrokBotAvailable)) {
        try { Invoke-GrokBotApi -Action interrupt -Agent $agent | Out-Null } catch { }
    }
    if ($status -and $status.shopJoinPid) {
        try { Stop-ProcessTree -ProcessId ([int]$status.shopJoinPid) } catch { }
    }
    if ($status -and $status.pid) {
        try { Stop-ProcessTree -ProcessId ([int]$status.pid) } catch { }
    }
    if ($status -and $status.agentPid -and $status.agentPid -ne $status.pid) {
        try { Stop-ProcessTree -ProcessId ([int]$status.agentPid) } catch { }
    }
    if ($status) {
        $status.state = 'stopped'
        $status.updatedAt = [DateTime]::UtcNow.ToString('o')
        Write-JsonFile $statusPath $status
    }
    return [pscustomobject]@{ ok = $true; sessionId = $SessionId; state = 'stopped' }
}
