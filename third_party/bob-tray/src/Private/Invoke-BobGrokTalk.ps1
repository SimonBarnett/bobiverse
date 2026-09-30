$script:BobGrokTalkLineCap = 350
$script:BobGrokTalkVersion = 1
$script:BobGrokTalkInboxName = 'grok-inbox.jsonl'
$script:BobGrokTalkOutboxName = 'grok-outbox.jsonl'
$script:BobGrokTalkStateName = 'grok-talk-worker.json'

function Test-BobTextLooksLikeSecret {
    param([string]$Text)
    if (-not $Text) { return $false }
    $lower = ([string]$Text).ToLowerInvariant()
    foreach ($m in @(
            'password='
            'xai_api_key='
            'connect.password'
            'x-bob-secret'
            'bob_report_secret'
            'report.secret'
            'psk='
            'pin='
        )) {
        if ($lower.Contains($m)) { return $true }
    }
    if (Test-PromptSecrets -Prompt $Text) { return $true }
    return $false
}

function Get-BobGrokTalkPaths {
    $home = Get-BobIrcHome
    return [pscustomobject]@{
        home   = $home
        inbox  = Join-Path $home $script:BobGrokTalkInboxName
        outbox = Join-Path $home $script:BobGrokTalkOutboxName
        state  = Join-Path $home $script:BobGrokTalkStateName
    }
}

function Read-BobGrokTalkJsonl {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $rows = @()
    foreach ($line in @(Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)) {
        $t = ([string]$line).Trim()
        if (-not $t) { continue }
        try { $rows += ,($t | ConvertFrom-Json) } catch { }
    }
    return $rows
}

function ConvertFrom-BobGrokTalkInboxJob {
    param($Doc)
    if (-not $Doc) { return $null }
    if ([int]$Doc.v -ne $script:BobGrokTalkVersion) { return $null }
    $jobId = [string]$Doc.job_id
    if (-not $jobId) { return $null }
    $reply = [string]$Doc.reply_target
    if (-not $reply) { return $null }
    return [pscustomobject]@{
        v            = $script:BobGrokTalkVersion
        job_id       = $jobId
        ts           = $Doc.ts
        asker        = [string]$Doc.asker
        channel      = [string]$Doc.channel
        body         = [string]$Doc.body
        nick         = [string]$Doc.nick
        machine_id   = [string]$Doc.machine_id
        reply_target = $reply
        body_hash    = [string]$Doc.body_hash
    }
}

function Get-BobGrokTalkCompletedJobIds {
    $paths = Get-BobGrokTalkPaths
    $done = @{}
    foreach ($row in @(Read-BobGrokTalkJsonl -Path $paths.outbox)) {
        $id = [string]$row.job_id
        if ($id) { $done[$id] = $true }
    }
    return $done
}

function Get-BobGrokTalkPendingJobs {
    param([string]$MachineId)
    if (-not $MachineId) {
        try { $MachineId = Get-ThisMachineId } catch { }
    }
    $paths = Get-BobGrokTalkPaths
    $done = Get-BobGrokTalkCompletedJobIds
    $pending = @()
    foreach ($row in @(Read-BobGrokTalkJsonl -Path $paths.inbox)) {
        $job = ConvertFrom-BobGrokTalkInboxJob $row
        if (-not $job) { continue }
        if ($MachineId -and [string]$job.machine_id -and [string]$job.machine_id -ne [string]$MachineId) { continue }
        if ($done.ContainsKey([string]$job.job_id)) { continue }
        $pending += $job
    }
    return @($pending | Sort-Object { [double]$_.ts })
}

function Get-BobGrokTalkWeeklyRemainingPct {
    try {
        $w = Get-BobWeeklyRemaining
        if ($w -and $null -ne $w.remaining_pct) { return [int]$w.remaining_pct }
    }
    catch { }
    return 0
}

function Get-BobGrokTalkCursorRemainingPct {
    try {
        $c = Get-BobCursorAgentWeeklyRemaining
        if ($c -and $null -ne $c.remaining_pct) { return [int]$c.remaining_pct }
    }
    catch { }
    return 0
}

function Select-BobGrokTalkFuel {
    $cur = Get-BobGrokTalkCursorRemainingPct
    $wk = Get-BobGrokTalkWeeklyRemainingPct
    if ($cur -gt 0) { return 'cursor-models' }
    if ($wk -gt 0) { return 'grok-build' }
    if ((Get-Command Test-GrokBotAvailable -ErrorAction SilentlyContinue) -and (Test-GrokBotAvailable)) {
        return 'grok-bot'
    }
    return $null
}

function Test-BobGrokTalkFuelAllowed {
    return ($null -ne (Select-BobGrokTalkFuel))
}

function Read-BobGrokTalkWorkerState {
    $paths = Get-BobGrokTalkPaths
    if (-not (Test-Path -LiteralPath $paths.state)) { return $null }
    try { return Read-JsonFile $paths.state } catch { return $null }
}

function Write-BobGrokTalkWorkerState {
    param($Doc)
    $paths = Get-BobGrokTalkPaths
    if (-not $Doc) {
        if (Test-Path -LiteralPath $paths.state) {
            Remove-Item -LiteralPath $paths.state -Force -ErrorAction SilentlyContinue
        }
        return
    }
    Write-JsonFile $paths.state $Doc
}

function Test-BobGrokTalkWorkerBusy {
    $st = Read-BobGrokTalkWorkerState
    return ($st -and $st.job_id)
}

function ConvertTo-BobGrokTalkOutLines {
    param([string]$Text)
    if (-not $Text) { return @() }
    $lines = @()
    foreach ($part in @($Text -split "`r?`n")) {
        $msg = ([string]$part).Replace("`r", ' ').Trim()
        if (-not $msg) { continue }
        if (Test-BobTextLooksLikeSecret $msg) { continue }
        if ($msg.Length -gt $script:BobGrokTalkLineCap) {
            $msg = $msg.Substring(0, $script:BobGrokTalkLineCap - 3) + '...'
        }
        $lines += $msg
    }
    return $lines
}

function Add-BobGrokTalkCompletion {
    param(
        [Parameter(Mandatory)]$Job,
        [Parameter(Mandatory)][string[]]$Lines
    )
    $paths = Get-BobGrokTalkPaths
    $safe = @()
    foreach ($ln in @($Lines)) {
        $msg = ([string]$ln).Replace("`r", ' ').Trim()
        if (-not $msg) { continue }
        if (Test-BobTextLooksLikeSecret $msg) { continue }
        if ($msg.Length -gt $script:BobGrokTalkLineCap) {
            $msg = $msg.Substring(0, $script:BobGrokTalkLineCap - 3) + '...'
        }
        $safe += $msg
    }
    if ($safe.Count -eq 0) { return $null }
    $doc = [pscustomobject]@{
        v            = $script:BobGrokTalkVersion
        job_id       = [string]$Job.job_id
        reply_target = [string]$Job.reply_target
        lines        = @($safe)
    }
    $line = ($doc | ConvertTo-Json -Compress -Depth 4)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::AppendAllText($paths.outbox, $line + [Environment]::NewLine, $utf8)
    return $doc
}

function New-BobGrokTalkPrompt {
    param([Parameter(Mandatory)]$Job)
    $asker = [string]$Job.asker
    $body = [string]$Job.body
    if (Test-BobTextLooksLikeSecret $body) {
        return $null
    }
    @"
IRC grok-talk reply for $($Job.nick) on $($Job.channel).
Reply with one plain English fact per line (no markdown). Max $($script:BobGrokTalkLineCap) characters per line.
From $($asker): $body
"@.Trim()
}

function Invoke-BobGrokTalkCursorSync {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$Cwd,
        [string]$Model,
        [int]$TimeoutSec = 600
    )
    return Invoke-BobCursorModelsOneShot -Prompt $Prompt -Cwd $Cwd -Model $Model -TimeoutSec $TimeoutSec
}

function Invoke-BobGrokTalkRunJob {
    param(
        [Parameter(Mandatory)]$Job,
        [Parameter(Mandatory)][string]$Fuel,
        [Parameter(Mandatory)][string]$Cwd
    )
    $prompt = New-BobGrokTalkPrompt -Job $Job
    if (-not $prompt) {
        return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'prompt blocked' }
    }
    $title = 'grok-talk-' + [string]$Job.job_id
    Write-BobGrokTalkWorkerState ([pscustomobject]@{
            job_id     = [string]$Job.job_id
            fuel       = $Fuel
            started_at = [DateTime]::UtcNow.ToString('o')
        })

    try {
        if ($env:BOB_GROK_TALK_TEST_THROW -match '^(?i)(1|true|after_state)$') {
            throw 'BT0gtalk inject worker throw'
        }

        $text = $null
        switch ($Fuel) {
            'grok-bot' {
                $agent = 'Bob'
                try {
                    $cfg = Read-JsonFile (Join-Path (Get-ModuleRoot) 'config\default.json')
                    if ($cfg -and $cfg.agents) {
                        foreach ($p in $cfg.agents.PSObject.Properties) {
                            if ([string]$p.Name -eq 'bob') { $agent = 'Bob'; break }
                        }
                    }
                }
                catch { }
                $r = Start-BobWorker -Cwd $Cwd -Prompt $prompt -Profile grok-talk -Title $title -Agent $agent -Force
                if ($r.ok -and $r.last_result -and $r.last_result.result) { $text = [string]$r.last_result.result }
            }
            'cursor-models' {
                $text = Invoke-BobGrokTalkCursorSync -Prompt $prompt -Cwd $Cwd
            }
            default {
                $model = Get-BobJobModel -Kind build -Fuel grok-build
                $r = Start-BobWorker -Cwd $Cwd -Prompt $prompt -Profile grok-talk -Title $title -Model $model -Force
                if ($r.ok -and $r.last_result -and $r.last_result.result) { $text = [string]$r.last_result.result }
            }
        }

        if (-not $text) {
            return [pscustomobject]@{ ok = $false; error = 'empty'; reason = 'no model text' }
        }
        $lines = @(ConvertTo-BobGrokTalkOutLines -Text $text)
        if ($lines.Count -eq 0) {
            return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'lines blocked' }
        }
        $comp = Add-BobGrokTalkCompletion -Job $Job -Lines $lines
        if (-not $comp) {
            return [pscustomobject]@{ ok = $false; error = 'refuse'; reason = 'completion blocked' }
        }
        return [pscustomobject]@{
            ok         = $true
            job_id     = [string]$Job.job_id
            fuel       = $Fuel
            completion = $comp
        }
    }
    finally {
        Write-BobGrokTalkWorkerState $null
    }
}
