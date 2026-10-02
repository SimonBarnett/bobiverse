function Stop-BobBuild {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$JobId
    )
    $job = Read-FleetJob -JobId $JobId
    if (-not $job) {
        return [pscustomobject]@{ ok = $false; error = 'not_found'; jobId = $JobId }
    }
    $path = Get-FleetJobPath -Lane cancel -Machine $job.machine -JobId $JobId
    Write-JsonFile $path @{ id = $JobId; machine = $job.machine; requestedAt = [DateTime]::UtcNow.ToString('o') }
    if ($job.sessionId -and $job.lane -eq 'running') {
        try { Stop-BobWorker -SessionId $job.sessionId | Out-Null } catch { }
    }
    Send-FleetReply -ReplyChannel $job.reply_channel -Text "stop requested for $JobId on $($job.machine)"
    return [pscustomobject]@{ ok = $true; jobId = $JobId; cancelled = $true }
}
