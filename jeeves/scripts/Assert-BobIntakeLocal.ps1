#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke: POST /bob/v1/intake locally and via public ARR; expect HTTP 202 (FR #1014).
.DESCRIPTION
  IIS ARR on irc.ntsa.uk rewrites /bob/v1/intake to 127.0.0.1:7700. When BobCallback is down,
  ARR returns 502.3 (0x80072efd). This assert proves the upstream is up and the rewrite works.
#>
[CmdletBinding()]
param(
    [string]$LocalBase = 'http://127.0.0.1:7700',
    [string]$PublicBase = 'https://irc.ntsa.uk',
    [switch]$SkipPublic
)

$ErrorActionPreference = 'Stop'

function Invoke-IntakeProbe {
    param([string]$Base, [string]$Title)
    $uri = ($Base.TrimEnd('/') + '/bob/v1/intake')
    $body = @{
        kind  = 'issue'
        repo  = 'SimonBarnett/bobiverse'
        title = $Title
        body  = 'Assert-BobIntakeLocal probe (FR #1014). Safe to close if noise.'
    } | ConvertTo-Json -Compress
    try {
        $resp = Invoke-WebRequest -Uri $uri -Method POST -ContentType 'application/json; charset=utf-8' -Body $body -UseBasicParsing -TimeoutSec 30
        return [pscustomobject]@{ ok = $true; status = [int]$resp.StatusCode; err = '' }
    } catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        return [pscustomobject]@{ ok = $false; status = $code; err = $_.Exception.Message }
    }
}

$failures = @()
$local = Invoke-IntakeProbe -Base $LocalBase -Title ('intake-assert-local-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
Write-Host ("INFO local intake status={0}" -f $local.status)
if ($local.status -ne 202) {
    $failures += ("local expected 202 got {0}: {1}" -f $local.status, $local.err)
}

if (-not $SkipPublic) {
    $pub = Invoke-IntakeProbe -Base $PublicBase -Title ('intake-assert-public-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
    Write-Host ("INFO public intake status={0}" -f $pub.status)
    if ($pub.status -ne 202) {
        $failures += ("public expected 202 got {0}: {1}" -f $pub.status, $pub.err)
    }
}

if ($failures.Count -gt 0) {
    Write-Host 'FAIL Assert-BobIntakeLocal:'
    $failures | ForEach-Object { Write-Host ("  - " + $_) }
    exit 1
}
Write-Host 'PASS Assert-BobIntakeLocal local(+public) HTTP 202'
exit 0