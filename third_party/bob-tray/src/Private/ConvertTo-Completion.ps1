function ConvertTo-Completion {
    param(
        [string]$SessionId,
        $GrokResult,
        [int]$ExitCode,
        [string]$Stdout,
        [string]$Stderr
    )

    $parsed = $null
    if ($GrokResult) { $parsed = $GrokResult }
    elseif ($Stdout -and $Stdout.Trim().StartsWith('{')) {
        try { $parsed = $Stdout | ConvertFrom-Json } catch { $parsed = $null }
    }

    $resultText = $null
    if ($parsed) {
        if ($parsed.PSObject.Properties.Name -contains 'result' -and $parsed.result) {
            $resultText = [string]$parsed.result
        }
        elseif ($parsed.PSObject.Properties.Name -contains 'text' -and $parsed.text) {
            $resultText = [string]$parsed.text
        }
    }

    $stop = $null
    if ($parsed) {
        if ($parsed.PSObject.Properties.Name -contains 'stop_reason') { $stop = [string]$parsed.stop_reason }
        elseif ($parsed.PSObject.Properties.Name -contains 'stopReason') { $stop = [string]$parsed.stopReason }
    }

    $status = 'blocked'
    $needsHuman = $false
    $summary = ''
    $next = $null

    $stopNorm = ''
    if ($stop) { $stopNorm = $stop.ToLowerInvariant() }

    if ($ExitCode -eq 130 -or $ExitCode -eq 143) {
        $status = 'stopped'
        $summary = "grok exit $ExitCode (stopped)"
        $needsHuman = $false
    }
    elseif ($ExitCode -ne 0 -or $stopNorm -eq 'error') {
        $status = 'failed'
        $cap = ''
        if ($Stderr) {
            $cap = $Stderr
            if ($cap.Length -gt 2000) { $cap = $cap.Substring(0, 2000) }
        }
        $summary = "grok exit $ExitCode"
        if ($stop) { $summary = "$summary stop=$stop" }
        if ($cap) { $summary = "$summary; $cap" }
        $needsHuman = $true
        $next = 'inspect stderr / outbox/raw.txt'
    }
    elseif (-not $resultText) {
        # Never invent ok=true. Missing result is blocked, not ok.
        $status = 'blocked'
        $summary = 'stdout missing result/text'
        $needsHuman = $true
        $next = 'save outbox/raw.txt and inspect'
    }
    else {
        $status = 'ok'
        $summary = $resultText
        $needsHuman = $false
        $next = 'Send-BobPrompt or Stop-BobWorker'
    }

    # Hard rule: failed/blocked/stopped must never be status=ok
    if ($status -ne 'ok' -and $status -eq 'ok') {
        $status = 'failed'
    }

    return [pscustomobject]@{
        id             = [guid]::NewGuid().ToString()
        session        = $SessionId
        status         = $status
        summary        = $summary
        evidence       = [pscustomobject]@{
            exitCode   = $ExitCode
            stopReason = $stop
            resumed    = $(if ($parsed -and ($parsed.PSObject.Properties.Name -contains 'resumed')) { [bool]$parsed.resumed } else { $false })
        }
        needs_human    = $needsHuman
        next_suggested = $next
    }
}

function Get-GrokResultText {
    param($Parsed, [string]$Stdout)
    if ($Parsed) {
        if ($Parsed.PSObject.Properties.Name -contains 'result' -and $Parsed.result) { return [string]$Parsed.result }
        if ($Parsed.PSObject.Properties.Name -contains 'text' -and $Parsed.text) { return [string]$Parsed.text }
    }
    return $null
}
