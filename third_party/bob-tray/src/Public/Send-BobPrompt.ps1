function Send-BobPrompt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SessionId,
        [Parameter(Mandatory)][string]$Prompt
    )

    $overlay = Read-Overlay
    $entry = @($overlay.workers | Where-Object { $_.sessionId -eq $SessionId }) | Select-Object -First 1
    if (-not $entry) {
        return [pscustomobject]@{ ok = $false; error = 'not_found'; sessionId = $SessionId }
    }
    if (Test-PromptSecrets -Prompt $Prompt) {
        return [pscustomobject]@{
            ok     = $false
            error  = 'refuse'
            reason = 'prompt contains password= or XAI_API_KEY; packet not written'
        }
    }

    $prof = Get-Profile -Name $entry.profile
    $cwdFull = [IO.Path]::GetFullPath($entry.cwd)
    $dir = Get-WorkerDir $SessionId
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'outbox') | Out-Null

    $agent = $null
    if ($entry.PSObject.Properties.Name -contains 'agent') { $agent = [string]$entry.agent }
    $useBot = ($entry.kind -eq 'grokbot') -or (Test-ShouldUseGrokBot -Agent $agent)
    if ($useBot) {
        if (-not $agent) { $agent = [string]$entry.title }
        $argv = @('grokbot', 'SendGrokBotUserMessage', $agent)
        [IO.File]::WriteAllText((Join-Path $dir 'outbox\argv.txt'), ($argv -join "`n"))
        Write-Audit -SessionId $SessionId -Cwd $cwdFull -Profile $entry.profile -Prompt $Prompt
        $raw = Invoke-GrokBotApi -Action send -Agent $agent -Text $Prompt -Wait -TimeoutSec $prof.TimeoutSec
        $mapped = ConvertFrom-GrokBotRun -Run $raw -SessionId $SessionId
        $written = Write-BobTurnResult -SessionId $SessionId -Cwd $cwdFull -Title $entry.title -Profile $entry.profile -Prompt $Prompt -Mapped $mapped -Kind 'grokbot' -Agent $agent -AgentId $mapped.GrokResult.agentId -Resumed $true
        return [pscustomobject]@{
            ok          = $written.ok
            sessionId   = $SessionId
            resumed     = $true
            completion  = $written.completion
            last_result = $written.last_result
            argv        = $argv
            transport   = 'grokbot'
            agent       = $agent
        }
    }

    $argv = Get-BobArgv -Prompt $Prompt -Cwd $cwdFull -SessionId $SessionId -Resume -Profile $prof
    [IO.File]::WriteAllText((Join-Path $dir 'outbox\argv.txt'), ($argv -join "`n"))
    Write-Audit -SessionId $SessionId -Cwd $cwdFull -Profile $entry.profile -Prompt $Prompt

    $run = Invoke-Grok -Args $argv -WorkingDirectory $cwdFull -TimeoutSec $prof.TimeoutSec
    [IO.File]::WriteAllText((Join-Path $dir 'outbox\raw.txt'), [string]$run.Stdout)

    $parsed = $null
    if ($run.Stdout -and $run.Stdout.Trim().StartsWith('{')) {
        try { $parsed = $run.Stdout | ConvertFrom-Json } catch { $parsed = $null }
    }

    $completion = ConvertTo-Completion -SessionId $SessionId -GrokResult $parsed -ExitCode $run.ExitCode -Stdout $run.Stdout -Stderr $run.Stderr
    Write-JsonFile (Join-Path $dir 'outbox\completion.json') $completion

    $last = [pscustomobject]@{
        sessionId   = $SessionId
        result      = (Get-GrokResultText -Parsed $parsed -Stdout $run.Stdout)
        stop_reason = $(if ($parsed -and $parsed.stop_reason) { $parsed.stop_reason } elseif ($parsed -and $parsed.stopReason) { $parsed.stopReason } else { $null })
        resumed     = $(if ($parsed -and ($parsed.PSObject.Properties.Name -contains 'resumed')) { [bool]$parsed.resumed } else { $false })
        exitCode    = $run.ExitCode
        durationMs  = $run.DurationMs
        argv        = $run.Argv
        completion  = $completion
    }
    Write-JsonFile (Join-Path $dir 'last_result.json') $last

    $status = [pscustomobject]@{
        sessionId = $SessionId
        kind      = 'oneshot'
        state     = $(if ($completion.status -eq 'ok') { 'done' } elseif ($completion.status -eq 'stopped') { 'stopped' } elseif ($completion.status -eq 'failed') { 'done' } else { 'blocked' })
        cwd       = $cwdFull
        title     = $entry.title
        updatedAt = [DateTime]::UtcNow.ToString('o')
    }
    Write-JsonFile (Join-Path $dir 'status.json') $status

    return [pscustomobject]@{
        ok          = ($completion.status -eq 'ok')
        sessionId   = $SessionId
        resumed     = $last.resumed
        completion  = $completion
        last_result = $last
        argv        = $argv
    }
}
