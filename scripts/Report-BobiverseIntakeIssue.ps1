<#
.SYNOPSIS
  POST kind=issue to https://irc.ntsa.uk/bob/v1/intake (honesty-box / no-gh path).

.DESCRIPTION
  Auth via X-Bob-Secret from env or file. On network/HTTP failure, writes the
  payload JSON under report-outbox and/or install-outbox for later retry
  (same idempotency_key).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Body,
    [string]$Repo = 'SimonBarnett/bobiverse',
    [ValidateSet('issue', 'fr', 'skill', 'harvest')]
    [string]$Kind = 'issue',
    [string]$IntakeUrl = 'https://irc.ntsa.uk/bob/v1/intake',
    [string]$IdempotencyKey = '',
    [string]$Machine = '',
    [string]$Agent = 'Report-BobiverseIntakeIssue',
    [string]$OutboxDir = '',
    [string]$InstallRoot = '',
    [string]$Secret = '',
    [int]$TimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-BobiverseIntakeSecret {
    param([string]$Explicit)
    if ($Explicit) { return $Explicit.Trim() }
    foreach ($name in @(
            'BOB_REPORT_SECRET',
            'BOB_CALLBACK_SECRET',
            'BOB_SECRET',
            'BOB_INTAKE_SECRET'
        )) {
        $v = [string][Environment]::GetEnvironmentVariable($name)
        if ($v -and $v.Trim()) { return $v.Trim() }
    }
    $candidates = @(
        (Join-Path $env:USERPROFILE '.grok\bob\report.secret'),
        (Join-Path $env:USERPROFILE '.grok\bob\bob.secret')
    )
    if ($env:BOB_DIGEST_HOME) {
        $candidates += @(
            (Join-Path $env:BOB_DIGEST_HOME 'bob.secret'),
            (Join-Path $env:BOB_DIGEST_HOME 'report.secret')
        )
    }
    if ($InstallRoot) {
        $candidates += @(
            (Join-Path $InstallRoot 'config\report.secret'),
            (Join-Path $InstallRoot 'config\bob.secret')
        )
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            $t = [IO.File]::ReadAllText($p).Trim()
            if ($t) { return $t }
        }
    }
    return ''
}

function New-BobiverseIntakePayload {
    $idem = $IdempotencyKey
    if (-not $idem) {
        $raw = ('{0}|{1}|{2}|{3}' -f $Kind, $Repo, $Title, $Body)
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($raw))
            $idem = 'ps-' + ([BitConverter]::ToString($hash) -replace '-', '').Substring(0, 24).ToLowerInvariant()
        }
        finally { $sha.Dispose() }
    }
    $mach = $Machine
    if (-not $mach) {
        if ($env:BOB_MACHINE_ID) { $mach = [string]$env:BOB_MACHINE_ID }
        else { $mach = [string]$env:COMPUTERNAME }
    }
    return [ordered]@{
        kind             = $Kind
        repo             = $Repo
        title            = $Title.Trim()
        body             = $Body
        idempotency_key  = $idem
        source           = [ordered]@{
            machine    = ([string]$mach).Substring(0, [Math]::Min(64, ([string]$mach).Length))
            agent      = ([string]$Agent).Substring(0, [Math]::Min(64, ([string]$Agent).Length))
            skill_book = 'harvest'
            version    = ''
        }
    }
}

function Write-BobiverseIntakeOutbox {
    param(
        [Parameter(Mandatory)]$Payload,
        [string[]]$Dirs
    )
    $written = @()
    $idem = [string]$Payload.idempotency_key
    $digest = $idem
    if ($digest.Length -gt 16) { $digest = $digest.Substring(0, 16) }
    $name = 'report-{0}.json' -f $digest
    $json = ($Payload | ConvertTo-Json -Depth 6)
    foreach ($dir in $Dirs) {
        if (-not $dir) { continue }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $path = Join-Path $dir $name
        [IO.File]::WriteAllText($path, $json + "`n", [Text.UTF8Encoding]::new($false))
        $written += $path
    }
    return $written
}

$payload = New-BobiverseIntakePayload
$secret = Get-BobiverseIntakeSecret -Explicit $Secret

$outDirs = New-Object System.Collections.Generic.List[string]
if ($OutboxDir) { [void]$outDirs.Add($OutboxDir) }
[void]$outDirs.Add((Join-Path $env:USERPROFILE '.grok\bob\report-outbox'))
if ($InstallRoot) {
    [void]$outDirs.Add((Join-Path $InstallRoot 'install-outbox'))
    [void]$outDirs.Add((Join-Path $InstallRoot 'report-outbox'))
}
else {
    # Repo / CWD fallback when InstallRoot unset
    [void]$outDirs.Add((Join-Path (Get-Location).Path 'report-outbox'))
    [void]$outDirs.Add((Join-Path (Get-Location).Path 'install-outbox'))
}

$headers = @{
    'Content-Type' = 'application/json'
}
if ($secret) {
    $headers['X-Bob-Secret'] = $secret
}
if ($env:BOB_INTAKE_KEY) {
    $headers['X-Bob-Intake-Key'] = [string]$env:BOB_INTAKE_KEY
}

$bodyJson = ($payload | ConvertTo-Json -Depth 6)
try {
    $resp = Invoke-RestMethod -Method Post -Uri $IntakeUrl -Headers $headers `
        -Body $bodyJson -TimeoutSec $TimeoutSec
    return [pscustomobject]@{
        ok              = $true
        queued_local    = $false
        intake_id       = $resp.intake_id
        url             = $resp.url
        queued          = [bool]$resp.queued
        idempotency_key = $payload.idempotency_key
        outbox          = @()
    }
}
catch {
    $paths = Write-BobiverseIntakeOutbox -Payload $payload -Dirs ($outDirs | Select-Object -Unique)
    return [pscustomobject]@{
        ok              = $false
        queued_local    = $true
        intake_id       = $null
        url             = $null
        queued          = $true
        idempotency_key = $payload.idempotency_key
        outbox          = $paths
        error           = [string]$_.Exception.Message
    }
}
