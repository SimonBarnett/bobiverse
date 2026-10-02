function Start-BobWorker {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Cwd,
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Profile = 'generic',
        [string]$Title,
        [string]$SessionId,
        [string]$Agent,
        [string]$Model,
        [switch]$Force,
        [switch]$WhatIfArgv
    )

    $root = Initialize-BridgeRoot
    $prof = Get-Profile -Name $Profile
    $cwdFull = [IO.Path]::GetFullPath($Cwd)
    if (-not $Title) {
        if ($Agent) { $Title = $Agent }
        else { $Title = "bob-$Profile" }
    }

    if (Test-PromptSecrets -Prompt $Prompt) {
        return [pscustomobject]@{
            ok    = $false
            error = 'refuse'
            reason = 'prompt contains password= or XAI_API_KEY; packet not written'
        }
    }

    $overlay = Read-Overlay
    $same = Test-SameCwd -Cwd $cwdFull -Overlay $overlay
    if (@($same).Count -gt 0 -and -not $Force) {
        return [pscustomobject]@{
            ok         = $false
            error      = 'worker_exists'
            sessionId  = @($same)[0].sessionId
            workerCount = @($overlay.workers).Count
        }
    }

    # MaxWorkersPerMachine 0 = unlimited (no per-machine worker ceiling).
    if ($prof.MaxWorkersPerMachine -gt 0 -and @($overlay.workers).Count -ge $prof.MaxWorkersPerMachine -and -not $Force) {
        return [pscustomobject]@{
            ok    = $false
            error = 'cap'
            reason = "max_workers_per_machine=$($prof.MaxWorkersPerMachine)"
        }
    }

    if (-not $SessionId) { $SessionId = [guid]::NewGuid().ToString() }
    $dir = Get-WorkerDir $SessionId
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'outbox') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'inbox') | Out-Null

    $useBot = Test-ShouldUseGrokBot -Agent $Agent
    $argv = $null
    if ($useBot) {
        $argv = @('grokbot', 'SendGrokBotUserMessage', $Agent)
    }
    else {
        if (-not $Model) { $Model = Get-BobJobModel -Kind build -Fuel grok-build }
        $argv = Get-BobArgv -Prompt $Prompt -Cwd $cwdFull -SessionId $SessionId -Profile $prof -Model $Model
    }
    $argvPath = Join-Path $dir 'outbox\argv.txt'
    [IO.File]::WriteAllText($argvPath, (($argv | ForEach-Object { $_ }) -join "`n"))

    if ($WhatIfArgv) {
        return [pscustomobject]@{
            ok        = $true
            whatIf    = $true
            sessionId = $SessionId
            argv      = $argv
            argvPath  = $argvPath
            transport = $(if ($useBot) { 'grokbot' } else { 'cli' })
        }
    }

    if ($Agent -and -not $useBot -and -not (Test-BobUsesFakeGrok)) {
        return [pscustomobject]@{
            ok    = $false
            error = 'grokbot_unavailable'
            reason = 'Grok Bot home/python missing; off-DEV Fake-Grok still uses -p'
        }
    }

    if ($useBot -and -not (Test-GrokBotAvailable)) {
        return [pscustomobject]@{
            ok     = $false
            error  = 'grokbot_unavailable'
            reason = 'Grok Bot is not signed in on this machine'
        }
    }

    try { Copy-BobProjectSkills | Out-Null } catch { }
    Write-Audit -SessionId $SessionId -Cwd $cwdFull -Profile $Profile -Prompt $Prompt

    # #70 MUST 2: shop IRC client for this git worker (grok-build / on-demand path)
    try { Start-BobWorkerIrcAgent -WorkerPid $PID } catch { }

    if ($useBot) {
        $raw = Invoke-GrokBotApi -Action send -Agent $Agent -Text $Prompt -Wait -TimeoutSec $prof.TimeoutSec
        $mapped = ConvertFrom-GrokBotRun -Run $raw -SessionId $SessionId
        $written = Write-BobTurnResult -SessionId $SessionId -Cwd $cwdFull -Title $Title -Profile $Profile -Prompt $Prompt -Mapped $mapped -Kind 'grokbot' -Agent $Agent -AgentId $mapped.GrokResult.agentId -RegisterWorker
        return [pscustomobject]@{
            ok          = $written.ok
            sessionId   = $SessionId
            completion  = $written.completion
            last_result = $written.last_result
            status      = $written.status
            argv        = $argv
            processGone = $true
            transport   = 'grokbot'
            agent       = $Agent
        }
    }

    $run = Invoke-Grok -Args $argv -WorkingDirectory $cwdFull -TimeoutSec $prof.TimeoutSec
    [IO.File]::WriteAllText((Join-Path $dir 'outbox\raw.txt'), [string]$run.Stdout)
    if ($run.Stderr) {
        [IO.File]::WriteAllText((Join-Path $dir 'outbox\stderr.txt'), [string]$run.Stderr)
    }

    $parsed = $null
    if ($run.Stdout -and $run.Stdout.Trim().StartsWith('{')) {
        try { $parsed = $run.Stdout | ConvertFrom-Json } catch { $parsed = $null }
    }
    if (-not $parsed -and $run.ExitCode -eq 0) {
        # stdout not JSON â†’ blocked via ConvertTo-Completion
    }

    $completion = ConvertTo-Completion -SessionId $SessionId -GrokResult $parsed -ExitCode $run.ExitCode -Stdout $run.Stdout -Stderr $run.Stderr
    Write-JsonFile (Join-Path $dir 'outbox\completion.json') $completion

    $last = [pscustomobject]@{
        sessionId  = $SessionId
        result     = (Get-GrokResultText -Parsed $parsed -Stdout $run.Stdout)
        stop_reason = $(if ($parsed -and $parsed.stop_reason) { $parsed.stop_reason } elseif ($parsed -and $parsed.stopReason) { $parsed.stopReason } else { $null })
        resumed    = $(if ($parsed -and ($parsed.PSObject.Properties.Name -contains 'resumed')) { [bool]$parsed.resumed } else { $false })
        exitCode   = $run.ExitCode
        durationMs = $run.DurationMs
        argv       = $run.Argv
        completion = $completion
    }
    Write-JsonFile (Join-Path $dir 'last_result.json') $last

    $state = switch ($completion.status) {
        'ok' { 'done' }
        'failed' { 'done' }
        'stopped' { 'stopped' }
        default { 'blocked' }
    }
    $status = [pscustomobject]@{
        sessionId = $SessionId
        kind      = 'oneshot'
        state     = $state
        cwd       = $cwdFull
        title     = $Title
        updatedAt = [DateTime]::UtcNow.ToString('o')
    }
    Write-JsonFile (Join-Path $dir 'status.json') $status

    $entry = [pscustomobject]@{
        sessionId = $SessionId
        title     = $Title
        cwd       = $cwdFull
        kind      = 'oneshot'
        profile   = $Profile
        createdAt = [DateTime]::UtcNow.ToString('o')
    }
    $workers = @($overlay.workers)
    $workers += $entry
    $overlay | Add-Member -NotePropertyName workers -NotePropertyValue $workers -Force
    Write-Overlay $overlay

    return [pscustomobject]@{
        ok          = ($completion.status -eq 'ok')
        sessionId   = $SessionId
        completion  = $completion
        last_result = $last
        status      = $status
        argv        = $argv
        processGone = $true
    }
}
