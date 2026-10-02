function Test-BobWatcherUp {
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(powershell|pwsh)\.exe$' -and
            $_.CommandLine -and
            $_.CommandLine -match 'Watch-BobJobs\.ps1' -and
            $_.CommandLine -notmatch '(?i)-Once\b'
        })
    return ($hits.Count -gt 0)
}

function Get-BobMachineRecord {
    $path = Join-Path (Get-BridgeRoot) 'machine.json'
    return (Read-JsonFile $path)
}

function Get-BobLastSeenAgeSec {
    param($Record)
    if (-not $Record -or -not $Record.lastSeen) { return $null }
    try {
        $t = [datetime]::Parse($Record.lastSeen, $null, [Globalization.DateTimeStyles]::RoundtripKind)
        if ($t.Kind -eq [DateTimeKind]::Unspecified) { $t = [datetime]::SpecifyKind($t, [DateTimeKind]::Utc) }
        return [int]([datetime]::UtcNow - $t.ToUniversalTime()).TotalSeconds
    }
    catch {
        return $null
    }
}
