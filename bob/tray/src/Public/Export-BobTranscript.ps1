function Export-BobTranscript {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SessionId,
        [string]$Output
    )
    $dir = Get-WorkerDir $SessionId
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'outbox') | Out-Null
    if (-not $Output) {
        $Output = Join-Path $dir 'outbox\transcript.md'
    }
    $status = Read-JsonFile (Join-Path $dir 'status.json')
    $last = Read-JsonFile (Join-Path $dir 'last_result.json')
    if ($status -and $status.kind -eq 'grokbot') {
        $name = $status.agent
        if (-not $name) { $name = $status.title }
        $body = @(
            "# Grok Bot transcript",
            "",
            "agent: $name",
            "session: $SessionId",
            "updated: $($status.updatedAt)",
            "",
            $(if ($last) { [string]$last.result } else { '_no last_result_' })
        ) -join "`r`n"
        [IO.File]::WriteAllText($Output, $body)
        return [pscustomobject]@{
            ok       = $true
            path     = $Output
            exitCode = 0
            stderr   = $null
        }
    }
    $r = Invoke-Grok -Args @('export', $SessionId, $Output) -WorkingDirectory $dir -TimeoutSec 60
    return [pscustomobject]@{
        ok        = ($r.ExitCode -eq 0)
        path      = $Output
        exitCode  = $r.ExitCode
        stderr    = $r.Stderr
    }
}
