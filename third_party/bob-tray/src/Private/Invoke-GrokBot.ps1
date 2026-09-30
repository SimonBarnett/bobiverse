function Get-GrokBotApiScript {
    Join-Path (Get-ModuleRoot) 'tools\GrokBotApi.py'
}

function Get-PythonExe {
    foreach ($c in @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
            'C:\Program Files\Python312\python.exe'
        )) {
        if ($c -and (Test-Path $c) -and $c -notmatch 'WindowsApps') { return $c }
    }
    foreach ($name in @('py', 'python')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { return $cmd.Source }
    }
    return $null
}

function Test-BobUsesFakeGrok {
    $exe = Get-GrokExe
    if ($env:BOB_TRANSPORT -and $env:BOB_TRANSPORT.Trim().ToLowerInvariant() -eq 'cli') {
        return $true
    }
    if ($exe -and ($exe -match 'Fake-Grok\.ps1$')) {
        return $true
    }
    return $false
}

function Test-GrokBotAvailable {
    if (Test-BobUsesFakeGrok) { return $false }
    $script = Get-GrokBotApiScript
    if (-not (Test-Path $script)) { return $false }
    if (-not (Get-PythonExe)) { return $false }
    if ($env:BOB_GROK_BOT_HOME -and (Test-Path (Join-Path $env:BOB_GROK_BOT_HOME 'sand-secrets.json'))) {
        return $true
    }
    $appdata = Join-Path $env:APPDATA 'Grok Bot\sand-secrets.json'
    if ($env:APPDATA -and (Test-Path $appdata)) { return $true }
    $redir = 'D:\Users\Administrator\AppData\Roaming\Grok Bot\sand-secrets.json'
    if (Test-Path $redir) { return $true }
    return $false
}

function Invoke-GrokBotApi {
    param(
        [Parameter(Mandatory)][string]$Action,
        [string]$Agent,
        [string]$Text,
        [switch]$Wait,
        [int]$TimeoutSec = 180
    )
    $py = Get-PythonExe
    if (-not $py) { throw 'python missing: needed for Grok Bot transport' }
    $script = Get-GrokBotApiScript
    if (-not (Test-Path $script)) { throw "missing $script" }

    $outDir = Join-Path ([IO.Path]::GetTempPath()) ('bob-grokbot-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $argList = New-Object System.Collections.Generic.List[string]
    [void]$argList.Add($script)
    [void]$argList.Add($Action)
    if ($Agent) { [void]$argList.Add('--agent'); [void]$argList.Add($Agent) }
    if ($Text) {
        $textPath = Join-Path $outDir 'prompt.txt'
        [IO.File]::WriteAllText($textPath, $Text)
        [void]$argList.Add('--text-file')
        [void]$argList.Add($textPath)
    }
    if ($Wait) { [void]$argList.Add('--wait') }
    if ($TimeoutSec -gt 0) { [void]$argList.Add('--timeout'); [void]$argList.Add([string]$TimeoutSec) }

    $quoted = @($argList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + (($_ -replace '\\', '\\') -replace '"', '\"') + '"' } else { $_ }
    }) -join ' '
    $stdoutPath = Join-Path $outDir 'stdout.txt'
    $stderrPath = Join-Path $outDir 'stderr.txt'
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $py -ArgumentList $quoted -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $limit = [Math]::Max(30, $TimeoutSec + 30)
    $exited = $proc.WaitForExit($limit * 1000)
    if (-not $exited) {
        try { Stop-ProcessTree -ProcessId $proc.Id } catch { }
        $sw.Stop()
        return [pscustomobject]@{
            ExitCode   = 124
            Stdout     = ''
            Stderr     = "timeout after ${limit}s"
            DurationMs = [int]$sw.ElapsedMilliseconds
            Parsed     = $null
        }
    }
    $proc.WaitForExit()
    $sw.Stop()
    $stdout = ''
    $stderr = ''
    if (Test-Path $stdoutPath) { $stdout = [IO.File]::ReadAllText($stdoutPath) }
    if (Test-Path $stderrPath) { $stderr = [IO.File]::ReadAllText($stderrPath) }
    $parsed = $null
    $trim = $stdout.Trim()
    if ($trim.StartsWith('{')) {
        try { $parsed = $trim | ConvertFrom-Json } catch { $parsed = $null }
    }
    return [pscustomobject]@{
        ExitCode   = [int]$proc.ExitCode
        Stdout     = $stdout
        Stderr     = $stderr
        DurationMs = [int]$sw.ElapsedMilliseconds
        Parsed     = $parsed
    }
}

function Test-ShouldUseGrokBot {
    param([string]$Agent)
    if (-not $Agent) { return $false }
    if (Test-BobUsesFakeGrok) { return $false }
    return $true
}

function Write-BobTurnResult {
    param(
        [string]$SessionId,
        [string]$Cwd,
        [string]$Title,
        [string]$Profile,
        [string]$Prompt,
        $Mapped,
        [string]$Kind = 'oneshot',
        [string]$Agent,
        [string]$AgentId,
        [bool]$Resumed = $false,
        [switch]$RegisterWorker
    )
    $dir = Get-WorkerDir $SessionId
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'outbox') | Out-Null
    [IO.File]::WriteAllText((Join-Path $dir 'outbox\raw.txt'), [string]$Mapped.Stdout)
    if ($Mapped.Stderr) {
        [IO.File]::WriteAllText((Join-Path $dir 'outbox\stderr.txt'), [string]$Mapped.Stderr)
    }
    $grok = $Mapped.GrokResult
    if ($Resumed -and $grok) {
        $grok | Add-Member -NotePropertyName resumed -NotePropertyValue $true -Force
    }
    $completion = ConvertTo-Completion -SessionId $SessionId -GrokResult $grok -ExitCode $Mapped.ExitCode -Stdout $Mapped.Stdout -Stderr $Mapped.Stderr
    Write-JsonFile (Join-Path $dir 'outbox\completion.json') $completion
    $last = [pscustomobject]@{
        sessionId   = $SessionId
        result      = (Get-GrokResultText -Parsed $grok -Stdout $Mapped.Stdout)
        stop_reason = $(if ($grok -and $grok.stop_reason) { $grok.stop_reason } else { $null })
        resumed     = [bool]$Resumed
        exitCode    = $Mapped.ExitCode
        durationMs  = $Mapped.DurationMs
        argv        = @('grokbot', $Kind, $Agent)
        completion  = $completion
        transport   = $Kind
        agent       = $Agent
        agentId     = $AgentId
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
        kind      = $Kind
        state     = $state
        cwd       = $Cwd
        title     = $Title
        updatedAt = [DateTime]::UtcNow.ToString('o')
        agent     = $Agent
        agentId   = $AgentId
    }
    Write-JsonFile (Join-Path $dir 'status.json') $status
    if ($RegisterWorker) {
        $overlay = Read-Overlay
        $entry = [pscustomobject]@{
            sessionId = $SessionId
            title     = $Title
            cwd       = $Cwd
            kind      = $Kind
            profile   = $Profile
            createdAt = [DateTime]::UtcNow.ToString('o')
            agent     = $Agent
            agentId   = $AgentId
        }
        $workers = @($overlay.workers) + @($entry)
        $overlay | Add-Member -NotePropertyName workers -NotePropertyValue $workers -Force
        Write-Overlay $overlay
    }
    return [pscustomobject]@{
        completion  = $completion
        last_result = $last
        status      = $status
        ok          = ($completion.status -eq 'ok')
    }
}

function ConvertFrom-GrokBotRun {
    param($Run, [string]$SessionId)
    $p = $Run.Parsed
    $text = $null
    $ok = $false
    if ($p -and $p.ok -and $p.text) {
        $text = [string]$p.text
        $ok = $true
    }
    $grok = [pscustomobject]@{
        sessionId   = $SessionId
        result      = $text
        stop_reason = $(if ($ok) { 'EndTurn' } elseif ($Run.ExitCode -eq 124 -or ($p -and $p.error -eq 'timeout')) { 'Error' } else { 'Error' })
        resumed     = $false
        transport   = 'grokbot'
        agent       = $(if ($p) { $p.agent } else { $null })
        agentId     = $(if ($p) { $p.agentId } else { $null })
        delivery    = $(if ($p) { $p.delivery } else { $null })
        error       = $(if ($p) { $p.error } else { $null })
    }
    return [pscustomobject]@{
        GrokResult = $grok
        ExitCode   = $(if ($ok) { 0 } elseif ($Run.ExitCode -ne 0) { [int]$Run.ExitCode } else { 1 })
        Stdout     = ($grok | ConvertTo-Json -Compress -Depth 8)
        Stderr     = [string]$Run.Stderr
        DurationMs = $Run.DurationMs
    }
}
