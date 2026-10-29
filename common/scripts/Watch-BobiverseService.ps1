#Requires -Version 5.1
<#
FR #5195: independent, start-only safety net. Run from the protected state copy;
do not load code from the installation that an update may be replacing.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$StateDir,
    [string]$ServiceName = 'ircBob'
)

function Add-WatchdogLine {
    param([string]$Path, [string]$Line)
    $bytes = (New-Object System.Text.UTF8Encoding $false).GetBytes($Line + "`n")
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        try {
            $stream = [IO.File]::Open($Path, [IO.FileMode]::Append, [IO.FileAccess]::Write,
                ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
            try { $stream.Write($bytes, 0, $bytes.Length) }
            finally { $stream.Dispose() }
            return $true
        }
        catch {
            if ($attempt -lt 2) { Start-Sleep -Milliseconds 50 }
        }
    }
    return $false
}

function Write-WatchdogEvent {
    param([string]$Event)
    # Never include exception text, AppParameters, or filesystem paths.
    $safeName = [regex]::Replace($ServiceName, '[^A-Za-z0-9_.-]', '_')
    if ($safeName.Length -gt 80) { $safeName = $safeName.Substring(0, 80) }
    try {
        $logPath = Join-Path $StateDir 'update.log'
        $written = Add-WatchdogLine -Path $logPath `
            -Line ("{0} watchdog service={1} {2}" -f [DateTime]::UtcNow.ToString('o'), $safeName, $Event)
        # Append preserves existing ACLs. Reapply the log-only grant in case the
        # updater rotated the log and this invocation created its replacement.
        if ($written -and $env:OS -eq 'Windows_NT') {
            & icacls.exe $logPath /grant:r '*S-1-5-32-545:R' 2>&1 | Out-Null
            $global:LASTEXITCODE = 0
        }
    }
    catch { }
}

function Get-WatchdogEarHome {
    $homePath = Join-Path $InstallRoot 'home'
    try {
        $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        $parameters = [string](Get-ItemProperty -LiteralPath $key -Name AppParameters -ErrorAction Stop).AppParameters
        if ($parameters -match '(?i)(?:^|\s)-BobHome\s+(?:"([^"]+)"|([^\s"]+))(?=\s|$)') {
            if ($Matches[1]) { $homePath = $Matches[1] }
            else { $homePath = $Matches[2] }
        }
    }
    catch { }
    return $homePath
}

function Send-WatchdogOutcome {
    param([string]$Outcome)
    $safeName = [regex]::Replace($ServiceName, '[^A-Za-z0-9_.-]', '_')
    if ($safeName.Length -gt 80) { $safeName = $safeName.Substring(0, 80) }
    try {
        $outbox = Join-Path (Get-WatchdogEarHome) 'outbox.txt'
        $written = Add-WatchdogLine -Path $outbox `
            -Line ("PRIVMSG #bobiverse :watchdog: service {0} {1}" -f $safeName, $Outcome)
        if (-not $written) { Write-WatchdogEvent 'announcement-failed' }
    }
    catch { Write-WatchdogEvent 'announcement-failed' }
}

function Invoke-BobiverseServiceWatchdog {
    try {
        $markerPath = Join-Path $StateDir 'downtime.json'
        if (Test-Path -LiteralPath $markerPath -ErrorAction Stop) {
            if ((Get-Item -LiteralPath $markerPath -ErrorAction Stop).Length -gt 4096) {
                throw 'Invalid marker'
            }
            $jsonOptions = @{ ErrorAction = 'Stop' }
            if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
                $jsonOptions.DateKind = 'String'
            }
            $marker = [IO.File]::ReadAllText($markerPath) | ConvertFrom-Json @jsonOptions
            $stamp = [DateTimeOffset]::MinValue
            $valid = $marker.atUtc -is [string] -and
                $marker.atUtc -match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|\+00:00)$' -and
                [DateTimeOffset]::TryParse($marker.atUtc, [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::None, [ref]$stamp)
            if (-not $valid) { throw 'Invalid marker' }
            $age = [DateTimeOffset]::UtcNow - $stamp
            if ($age.TotalSeconds -ge 0 -and $age.TotalMinutes -lt 10) {
                Write-WatchdogEvent 'update-active'
                return
            }
            Write-WatchdogEvent 'marker-expired-or-future'
        }
    }
    catch {
        # An unreadable/invalid marker cannot suppress recovery forever. Checking
        # and starting a stopped service is safe; no installed files are touched.
        Write-WatchdogEvent 'marker-invalid-or-unreadable'
    }

    try {
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        if ([string]$service.Status -eq 'Running') { return }
        if ([string]$service.Status -ne 'Stopped') {
            Write-WatchdogEvent 'service-not-stopped'
            return
        }
        Start-Service -Name $ServiceName -ErrorAction Stop
        $service.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,
            [TimeSpan]::FromSeconds(60))
        $service.Refresh()
        if ([string]$service.Status -ne 'Running') { throw 'Service not running' }
        Write-WatchdogEvent 'recovered'
        Send-WatchdogOutcome 'recovered (Running)'
    }
    catch {
        Write-WatchdogEvent 'recovery-failed'
        Send-WatchdogOutcome 'recovery failed'
    }
}

Invoke-BobiverseServiceWatchdog
