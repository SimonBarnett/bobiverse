#Requires -Version 5.1
<#
.SYNOPSIS
  Probe local bobcallback digest; announce on chair-outbox if down.
#>
[CmdletBinding()]
param(
    [string]$LocalUrl = 'http://127.0.0.1:7700/bob/v1/report',
    [string]$PublicUrl = 'https://irc.ntsa.uk/bob/v1/report',
    [string]$DigestHome = '',
    [int]$CooldownCooldownMinutes = 10
)

$ErrorActionPreference = 'Continue'
if (-not $DigestHome) {
    if ($env:BOB_DIGEST_HOME) { $DigestHome = $env:BOB_DIGEST_HOME }
    else { $DigestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
}
$fail = $false
$detail = @()
foreach ($u in @($LocalUrl, $PublicUrl)) {
    try {
        $r = Invoke-WebRequest -Uri $u -Method GET -TimeoutSec 8 -UseBasicParsing
        if ($r.StatusCode -ne 200) { $fail = $true; $detail += "$u status=$($r.StatusCode)" }
    } catch {
        $fail = $true
        $detail += "$u err=$($_.Exception.Message)"
    }
}
if (-not $fail) {
    Write-Host 'INFO webhooks OK'
    exit 0
}
Write-Host ("WARN webhooks degraded: " + ($detail -join '; '))
$stamp = Join-Path $DigestHome 'webhook-down.stamp'
$announce = $true
if (Test-Path -LiteralPath $stamp) {
    $age = (Get-Date).ToUniversalTime() - (Get-Item $stamp).LastWriteTimeUtc
    if ($age -lt [TimeSpan]::FromMinutes($AnnounceCooldownMinutes)) { $announce = $false }
}
if ($announce) {
    New-Item -ItemType Directory -Force -Path $DigestHome | Out-Null
    $msg = 'Jeeves: webhook probe failed — ' + (($detail -join '; ').Substring(0, [Math]::Min(200, ($detail -join '; ').Length)))
    Add-Content -LiteralPath (Join-Path $DigestHome 'chair-outbox.txt') -Value ("PRIVMSG #bobiverse :" + $msg) -Encoding utf8
    [IO.File]::WriteAllText($stamp, [datetime]::UtcNow.ToString('o'))
}
exit 1