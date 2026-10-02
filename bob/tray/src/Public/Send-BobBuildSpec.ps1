function Send-BobBuildSpec {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$JobId,
        [Parameter(Mandatory)][string]$Prompt
    )
    if (Test-PromptSecrets -Prompt $Prompt) {
        return [pscustomobject]@{ ok = $false; error = 'refuse' }
    }
    $job = Read-FleetJob -JobId $JobId
    if (-not $job) {
        return [pscustomobject]@{ ok = $false; error = 'not_found'; jobId = $JobId }
    }
    if ($job.lane -eq 'outbox') {
        return [pscustomobject]@{ ok = $false; error = 'already_done'; jobId = $JobId }
    }
    $followDir = Join-Path (Initialize-FleetRoot) (Join-Path 'followup' (ConvertTo-MachineId $job.machine))
    New-Item -ItemType Directory -Force -Path $followDir | Out-Null
    $follow = Join-Path $followDir ($JobId + '.json')
    $list = @()
    $existing = Read-JsonFile $follow
    if ($existing) { $list = @($existing) }
    $list += [pscustomobject]@{
        prompt    = $Prompt
        createdAt = [DateTime]::UtcNow.ToString('o')
    }
    Write-JsonFile $follow $list
    Write-Audit -SessionId $JobId -Cwd $job.cwd -Profile $job.profile -Prompt $Prompt
    return [pscustomobject]@{ ok = $true; jobId = $JobId; followups = $list.Count }
}
