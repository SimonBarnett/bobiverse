#Requires -Version 5.1
<#
.SYNOPSIS
  FR #5775: shared PowerShell airc verb/entry fail intake (same key as airc_fail_intake.py).

.DESCRIPTION
  Dedupe key: airc-<verb>-fail|<machine>|<verb>|<version>|<exception-class>
  Prefer native HTTP intake; falls back to Report-BobiverseIntakeIssue.ps1 when present.
  Never throws to the caller. Secrets are redacted.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Verb,
    [Parameter(Mandatory = $true)][string]$ExceptionClass,
    [string]$Detail = '',
    [string]$Machine = '',
    [string]$Version = '',
    [string]$ArgsJson = '',
    [string]$Traceback = '',
    [string]$Repo = 'SimonBarnett/bobiverse'
)
$ErrorActionPreference = 'Continue'

# FR #5783: never file live intake from pytest (same spirit as CheckFailIntake DryRun / FR #5641).
if ($env:PYTEST_CURRENT_TEST) {
    Write-Output (@{ ok = $false; skipped = 'pytest'; verb = $Verb } | ConvertTo-Json -Compress)
    return
}

function Get-AircFailSafeToken([string]$Tok, [string]$Default = '-') {
    $t = ([string]$Tok).Trim().ToLowerInvariant()
    $t = [regex]::Replace($t, '[^a-z0-9._-]+', '-')
    $t = $t.Trim('-')
    if (-not $t) { return $Default }
    return $t
}

function Get-AircFailRedacted([string]$Text) {
    $s = [string]$Text
    $s = [regex]::Replace($s, '(?i)\b(password|passwd|pwd|pass|secret|token|authorization)\s*[=:]\s*\S+', '$1=<redacted>')
    return $s
}

try {
    if (-not $Machine) {
        $Machine = $env:BOB_MACHINE_ID
        if (-not $Machine) { $Machine = $env:COMPUTERNAME }
        if (-not $Machine) { $Machine = 'unknown' }
    }
    if (-not $Version) {
        foreach ($cand in @(
                (Join-Path (Split-Path -Parent $PSScriptRoot) 'VERSION'),
                (Join-Path $PSScriptRoot '..\VERSION'),
                (Join-Path $env:ProgramFiles 'Bobiverse\airc\VERSION')
            )) {
            if (Test-Path -LiteralPath $cand) {
                $Version = (Get-Content -LiteralPath $cand -TotalCount 1 -ErrorAction SilentlyContinue)
                break
            }
        }
        if (-not $Version) { $Version = '-' }
    }
    $v = Get-AircFailSafeToken $Verb 'unknown'
    $mid = Get-AircFailSafeToken $Machine 'unknown'
    $ver = Get-AircFailSafeToken $Version '-'
    $exc = Get-AircFailSafeToken $ExceptionClass 'Exception'
    $key = ('airc-{0}-fail|{1}|{0}|{2}|{3}' -f $v, $mid, $ver, $exc)
    if ($key.Length -gt 128) { $key = $key.Substring(0, 128) }

    $title = Get-AircFailRedacted ("airc {0} fail {1} machine={2}" -f $v, $exc, $mid)
    if ($title.Length -gt 200) { $title = $title.Substring(0, 200) }
    $safeDetail = Get-AircFailRedacted $Detail
    if ($safeDetail.Length -gt 800) { $safeDetail = $safeDetail.Substring(0, 800) }
    $safeTb = Get-AircFailRedacted $Traceback
    if ($safeTb.Length -gt 4000) { $safeTb = $safeTb.Substring(0, 4000) }
    $safeArgs = Get-AircFailRedacted $ArgsJson
    $body = @"
FR #5775 airc verb failure (deterministic intake).
verb=$v
machine=$mid
version=$ver
exception_class=$exc
dedupe_key=$key
args=$safeArgs
detail=$safeDetail

### traceback (redacted)
``````
$safeTb
``````

---
_via-Report-AircVerbFailure FR=#5775_
"@

    $report = Join-Path $PSScriptRoot 'Report-BobiverseIntakeIssue.ps1'
    if (-not (Test-Path -LiteralPath $report)) {
        $alt = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Report-BobiverseIntakeIssue.ps1'
        if (Test-Path -LiteralPath $alt) { $report = $alt }
    }
    if (Test-Path -LiteralPath $report) {
        & $report -Kind issue -Repo $Repo -Title $title -Body $body -IdempotencyKey $key 2>$null | Out-Null
    } else {
        $url = $env:BOB_INTAKE_URL
        if (-not $url) { $url = 'https://irc.ntsa.uk/bob/v1/intake' }
        $payload = @{
            kind            = 'issue'
            repo            = $Repo
            title           = $title
            body            = $body
            idempotency_key = $key
            dedupe_key      = $key
            machine         = $mid
            agent           = 'Report-AircVerbFailure'
        } | ConvertTo-Json -Compress
        try {
            Invoke-RestMethod -Method Post -Uri $url -Body $payload -ContentType 'application/json; charset=utf-8' -TimeoutSec 8 | Out-Null
        } catch {
            $spoolRoot = Join-Path $env:LOCALAPPDATA 'Bobiverse\crash-spool'
            New-Item -ItemType Directory -Force -Path $spoolRoot | Out-Null
            $spool = Join-Path $spoolRoot ("airc-fail-{0}-{1}.json" -f $v, [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
            @{
                title = $title; body = $body; repo = $Repo; sig = $key; exe = 'airc'
                error = $_.Exception.GetType().Name; ts = [DateTime]::UtcNow.ToString('o')
            } | ConvertTo-Json | Set-Content -LiteralPath $spool -Encoding utf8
        }
    }
} catch {
    # never throw
}
