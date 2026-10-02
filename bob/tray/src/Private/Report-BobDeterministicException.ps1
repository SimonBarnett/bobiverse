# FR #401: unexpected exceptions in deterministic BobBridge/tools code open a
# GitHub issue via gh (templated body, no LLM). Fingerprint dedupe under
# ~/.grok/bob-bridge/exception-issues/

function Get-BobDeterministicExceptionOwningRepo {
    param(
        [string]$Site = '',
        [string]$ScriptPath = ''
    )
    $blob = ('{0} {1}' -f $Site, $ScriptPath).ToLowerInvariant()
    if ($blob -match 'watch-agenthealth|agentmonitor') {
        return 'SimonBarnett/AgentMonitor'
    }
    if ($blob -match 'agentic.irc|irc_agent|irc_listen|\\agentic_irc') {
        return 'SimonBarnett/agentic_irc'
    }
    if ($blob -match 'gh-jeeves|jeeves|digest\.py|bobjeeves') {
        return 'SimonBarnett/gh-Jeeves'
    }
    return 'SimonBarnett/agentic_build'
}

function Get-BobDeterministicExceptionFingerprint {
    param(
        [string]$Site,
        [string]$Message,
        [string]$ScriptPath = ''
    )
    $raw = ('{0}|{1}|{2}' -f $Site, $ScriptPath, $Message).ToLowerInvariant()
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($raw)
        $hash = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash) -replace '-', '').Substring(0, 32).ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Get-BobDeterministicExceptionStateDir {
    if ($env:BOB_EXCEPTION_ISSUE_DIR) {
        $dir = [string]$env:BOB_EXCEPTION_ISSUE_DIR
    }
    else {
        $dir = Join-Path $env:USERPROFILE '.grok\bob-bridge\exception-issues'
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Test-BobDeterministicExceptionRecentlyFiled {
    param(
        [Parameter(Mandatory)][string]$Fingerprint,
        [int]$DedupeHours = 12
    )
    $path = Join-Path (Get-BobDeterministicExceptionStateDir) ($Fingerprint + '.json')
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try {
        $doc = Get-Content -LiteralPath $path -Raw -Encoding utf8 | ConvertFrom-Json
        $ts = [datetime]::Parse([string]$doc.ts, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
        return ((Get-Date).ToUniversalTime() - $ts.ToUniversalTime()).TotalHours -lt $DedupeHours
    }
    catch { return $false }
}

function Save-BobDeterministicExceptionFingerprint {
    param(
        [Parameter(Mandatory)][string]$Fingerprint,
        [string]$IssueUrl = '',
        [string]$Repo = ''
    )
    $path = Join-Path (Get-BobDeterministicExceptionStateDir) ($Fingerprint + '.json')
    $doc = [ordered]@{
        ts       = [datetime]::UtcNow.ToString('o')
        issueUrl = $IssueUrl
        repo     = $Repo
        machine  = $env:COMPUTERNAME
    }
    ($doc | ConvertTo-Json -Compress) | Set-Content -LiteralPath $path -Encoding utf8
}

function New-BobDeterministicExceptionIssueBody {
    param(
        [Parameter(Mandatory)][string]$Site,
        [Parameter(Mandatory)][string]$Message,
        [string]$ScriptPath = '',
        [string]$Stack = '',
        [string]$Machine = ''
    )
    if (-not $Machine) { $Machine = [string]$env:COMPUTERNAME }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('## Deterministic exception (no LLM)')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine(('| Field | Value |'))
    [void]$sb.AppendLine(('|-------|-------|'))
    [void]$sb.AppendLine(('| machine | `{0}` |' -f $Machine.Replace('`', '''')))
    [void]$sb.AppendLine(('| site | `{0}` |' -f ($Site -replace '[`\r\n]', ' ')))
    if ($ScriptPath) {
        [void]$sb.AppendLine(('| script | `{0}` |' -f ($ScriptPath -replace '[`\r\n]', ' ')))
    }
    [void]$sb.AppendLine(('| when | `{0}` |' -f [datetime]::UtcNow.ToString('o')))
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('### Message')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('```')
    [void]$sb.AppendLine(($Message -replace '```', "'''"))
    [void]$sb.AppendLine('```')
    if ($Stack) {
        [void]$sb.AppendLine('')
        [void]$sb.AppendLine('### Stack')
        [void]$sb.AppendLine('')
        [void]$sb.AppendLine('```')
        [void]$sb.AppendLine(($Stack -replace '```', "'''"))
        [void]$sb.AppendLine('```')
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('Filed by `Report-BobDeterministicException` (FR #401). No LLM.')
    return $sb.ToString()
}

function Report-BobDeterministicException {
    <#
    .SYNOPSIS
      Open a templated GitHub issue for an unexpected deterministic exception (no LLM).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Site,
        [Parameter(Mandatory)]$Exception,
        [string]$ScriptPath = '',
        [string]$Repo = '',
        [int]$DedupeHours = 12,
        [switch]$Force
    )
    $msg = ''
    $stack = ''
    if ($Exception -is [System.Exception]) {
        $msg = [string]$Exception.Message
        $stack = [string]$Exception.ScriptStackTrace
        if (-not $stack) { $stack = [string]$Exception.StackTrace }
    }
    elseif ($Exception -is [System.Management.Automation.ErrorRecord]) {
        $msg = [string]$Exception.Exception.Message
        $stack = [string]$Exception.ScriptStackTrace
    }
    else {
        $msg = [string]$Exception
    }
    if (-not $msg) { $msg = '(no message)' }
    if (-not $Repo) {
        $Repo = Get-BobDeterministicExceptionOwningRepo -Site $Site -ScriptPath $ScriptPath
    }
    $fp = Get-BobDeterministicExceptionFingerprint -Site $Site -Message $msg -ScriptPath $ScriptPath
    if (-not $Force -and (Test-BobDeterministicExceptionRecentlyFiled -Fingerprint $fp -DedupeHours $DedupeHours)) {
        return [pscustomobject]@{
            ok           = $true
            deduped      = $true
            fingerprint  = $fp
            repo         = $Repo
            issueUrl     = $null
            reason       = 'recent fingerprint'
        }
    }
    $gh = Get-BobGhExe
    if (-not $gh) {
        return [pscustomobject]@{
            ok          = $false
            deduped     = $false
            fingerprint = $fp
            repo        = $Repo
            issueUrl    = $null
            reason      = 'gh.exe missing'
        }
    }
    $title = ('ex: {0} - {1}' -f $Site, ($msg.Substring(0, [Math]::Min(80, $msg.Length)))) -replace '[\r\n]+', ' '
    $body = New-BobDeterministicExceptionIssueBody -Site $Site -Message $msg -ScriptPath $ScriptPath -Stack $stack
    $tmp = Join-Path $env:TEMP ('bob-ex-' + $fp + '.md')
    try {
        [IO.File]::WriteAllText($tmp, $body, [Text.UTF8Encoding]::new($false))
        $url = & $gh issue create --repo $Repo --title $title --body-file $tmp 2>&1
        if ($LASTEXITCODE -ne 0) {
            return [pscustomobject]@{
                ok          = $false
                deduped     = $false
                fingerprint = $fp
                repo        = $Repo
                issueUrl    = $null
                reason      = ('gh issue create failed: {0}' -f $url)
            }
        }
        $issueUrl = ([string]$url).Trim()
        Save-BobDeterministicExceptionFingerprint -Fingerprint $fp -IssueUrl $issueUrl -Repo $Repo
        return [pscustomobject]@{
            ok          = $true
            deduped     = $false
            fingerprint = $fp
            repo        = $Repo
            issueUrl    = $issueUrl
            reason      = $null
        }
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}
