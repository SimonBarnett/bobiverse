#Requires -Version 5.1
<#
.SYNOPSIS
  Systray / shortcut Restart: announce via running ear if possible, then Restart-Service ircBob.
.NOTES
  FR #2943 / VISION S3: write depart-request + departure PRIVMSG to the *service* ear home
  (InstallRoot\home under LocalSystem Start-Bob), not %USERPROFILE%\.bobiverse. Aligns with
  Watch-BobTray Write-BobTrayIrcDepartureAnnounce (outbox + drain) then Restart-Service.
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'ircBob',
    [string]$Reason = 'tray-restart',
    [int]$DrainTimeoutSec = 20
)

$ErrorActionPreference = 'Stop'
Write-Host "INFO restart $ServiceName reason=$Reason"
# Do not use $Home — automatic variable is read-only in PowerShell.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$common = Join-Path $scriptDir 'Bobiverse-Common.ps1'
if (Test-Path -LiteralPath $common) { . $common }

$InstallRoot = Split-Path -Parent $scriptDir
$BobHome = ''
if (Get-Command Get-BobiverseEarServiceHome -ErrorAction SilentlyContinue) {
    $BobHome = [string](Get-BobiverseEarServiceHome -ServiceName $ServiceName -InstallRoot $InstallRoot)
}
if (-not $BobHome) {
    $BobHome = Join-Path $InstallRoot 'home'
}
New-Item -ItemType Directory -Force -Path $BobHome | Out-Null
Write-Host "INFO ear service home=$BobHome"

# Signal file for ear (_maybe_depart_request) + direct outbox announce (FR #2943 / tray parity).
$flag = Join-Path $BobHome 'depart-request.txt'
[IO.File]::WriteAllText($flag, $Reason + "`n", [Text.UTF8Encoding]::new($false))

$mid = ([string]$env:BOB_MACHINE_ID).Trim()
if (-not $mid) {
    $mid = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}
if (-not $mid) { $mid = 'unknown' }
$nick = 'Bob-{0}' -f $mid
$msg = '{0}: ear Restart - logging off IRC (graceful PART/QUIT) reason={1}' -f $nick, $Reason
$line = 'PRIVMSG #bobiverse :{0}' -f $msg
$outbox = Join-Path $BobHome 'outbox.txt'
try {
    if (Test-Path -LiteralPath $outbox) {
        $len = 0
        try { $len = ([IO.FileInfo]$outbox).Length } catch { }
        if ($len -gt 0) {
            $bak = Join-Path $BobHome ('outbox.bak-depart-ear-{0}.txt' -f [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
            try { [IO.File]::Copy($outbox, $bak, $true) } catch { }
        }
    }
    [IO.File]::WriteAllText($outbox, $line + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host ("INFO departure announce: {0}" -f $msg)
    $deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(1, $DrainTimeoutSec))
    while ([datetime]::UtcNow -lt $deadline) {
        if (-not (Test-Path -LiteralPath $outbox)) { break }
        $raw = ''
        try { $raw = [IO.File]::ReadAllText($outbox) } catch { }
        if ([string]::IsNullOrWhiteSpace($raw) -or $raw.IndexOf($line, [StringComparison]::Ordinal) -lt 0) { break }
        Start-Sleep -Milliseconds 250
    }
}
catch {
    Write-Warning ("departure announce failed: {0}" -f $_.Exception.Message)
}

Start-Sleep -Seconds 1
Restart-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Service $ServiceName | Format-Table Name, Status -AutoSize
