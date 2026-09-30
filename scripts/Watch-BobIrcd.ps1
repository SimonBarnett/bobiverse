#Requires -Version 5.1
<#
.SYNOPSIS
  Ensure BobIrcd is Running; restart if stopped; optionally append chair announce.
#>
[CmdletBinding()]
param(
    [string]$DigestHome = '',
    [int]$CooldownDownCooldownMinutes = 5
)

$ErrorActionPreference = 'Continue'
$svc = Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host 'WARN BobIrcd service not installed'
    exit 0
}
if ($svc.Status -eq 'Running') {
    Write-Host 'INFO BobIrcd Running'
    exit 0
}
Write-Host "WARN BobIrcd status=$($svc.Status) — attempting Start-Service"
try {
    Start-Service -Name 'BobIrcd' -ErrorAction Stop
    Start-Sleep -Seconds 2
} catch {
    try { Restart-Service -Name 'BobIrcd' -Force -ErrorAction Stop } catch {
        Write-Host "ERR BobIrcd restart failed: $($_.Exception.Message)"
        exit 1
    }
}
$svc2 = Get-Service -Name 'BobIrcd' -ErrorAction SilentlyContinue
if ($svc2 -and $svc2.Status -eq 'Running') {
    Write-Host 'INFO BobIrcd restarted OK'
    if (-not $DigestHome) {
        if ($env:BOB_DIGEST_HOME) { $DigestHome = $env:BOB_DIGEST_HOME }
        else { $DigestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
    }
    $stamp = Join-Path $DigestHome 'bobircd-restart.stamp'
    $cooldown = [TimeSpan]::FromMinutes($AnnounceDownCooldownMinutes)
    $announce = $true
    if (Test-Path -LiteralPath $stamp) {
        $age = (Get-Date).ToUniversalTime() - (Get-Item $stamp).LastWriteTimeUtc
        if ($age -lt $cooldown) { $announce = $false }
    }
    if ($announce) {
        New-Item -ItemType Directory -Force -Path $DigestHome | Out-Null
        $line = 'PRIVMSG #bobiverse :Jeeves: BobIrcd was down; restarted'
        Add-Content -LiteralPath (Join-Path $DigestHome 'chair-outbox.txt') -Value $line -Encoding utf8
        [IO.File]::WriteAllText($stamp, [datetime]::UtcNow.ToString('o'))
    }
    exit 0
}
Write-Host 'ERR BobIrcd still not Running'
exit 1