<#
.SYNOPSIS
  POST kind=issue|fr|skill|harvest to https://irc.ntsa.uk/bob/v1/intake (honesty-box / no-gh path).

.DESCRIPTION
  Intake is open: NO password/secret is sent or needed. (Optional X-Bob-Intake-Key
  only when BOB_INTAKE_KEY is set by the host.) On network/HTTP failure, writes the
  payload JSON under report-outbox and/or install-outbox for later retry
  (same idempotency_key).

  FR #611: POST body is UTF-8 bytes; HTTP error responses surface the intake JSON
  ``error`` field (e.g. bad_title) instead of only "(400) Bad Request".
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Body,
    [Parameter(Mandatory = $true)][string]$Repo,
    [ValidateSet('issue', 'fr', 'skill', 'harvest')]
    [string]$Kind = 'issue',
    # FR #3318: optional skill book. Empty -> derive from -Repo product defaults
    # (skills-visionary / a-search / ...); bobiverse stays harvest. Never hardcode
    # harvest for a product Plan-seat lesson repo.
    [string]$Book = '',
    [string]$IntakeUrl = 'https://irc.ntsa.uk/bob/v1/intake',
    [string]$IdempotencyKey = '',
    [string]$Machine = '',
    [string]$Agent = 'Report-BobiverseIntakeIssue',
    [string]$OutboxDir = '',
    [string]$InstallRoot = '',
    [int]$TimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ($Repo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) {
    throw "Repo must be owner/name (got '$Repo'). Intake requires an explicit target repo."
}

$titleTrim = $Title.Trim()
if (-not $titleTrim) {
    throw "Title is empty after trim (intake rejects bad_title)."
}
if ($titleTrim.Length -gt 200) {
    throw ("Title length {0} exceeds intake max 200 (bad_title). Shorten the title." -f $titleTrim.Length)
}

function Get-ExceptionHttpResponse {
    # FR #2461 / #1842: StrictMode - Exception.Response is absent on many exception types.
    param($Exception)
    if ($null -eq $Exception) { return $null }
    $prop = $Exception.PSObject.Properties['Response']
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Get-BobiverseIntakeErrorDetail {
    param($ErrorRecord)
    $detail = ''
    if ($ErrorRecord -and $ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        $detail = [string]$ErrorRecord.ErrorDetails.Message
    }
    $ex0 = if ($ErrorRecord) { $ErrorRecord.Exception } else { $null }
    $httpResp = Get-ExceptionHttpResponse -Exception $ex0
    if (-not $detail -and $null -ne $httpResp) {
        try {
            $stream = $httpResp.GetResponseStream()
            if ($stream) {
                # Response stream may already be consumed; best-effort.
                $reader = New-Object System.IO.StreamReader($stream)
                $detail = $reader.ReadToEnd()
            }
        } catch { }
    }
    $intakeError = $null
    if ($detail -match '"error"\s*:\s*"([^"]+)"') {
        $intakeError = $Matches[1]
    }
    $status = $null
    $ex = $ex0
    while ($null -ne $ex) {
        $resp = Get-ExceptionHttpResponse -Exception $ex
        if ($null -ne $resp) {
            $codeProp = $resp.PSObject.Properties['StatusCode']
            if ($null -ne $codeProp -and $null -ne $codeProp.Value) {
                try { $status = [int]$codeProp.Value; break } catch { }
                try { $status = [int]$codeProp.Value.value__; break } catch { }
            }
        }
        $ex = $ex.InnerException
    }
    if ($null -eq $status -and $ErrorRecord -and $ErrorRecord.Exception.Message -match '\((\d{3})\)') {
        $status = [int]$Matches[1]
    }
    return [pscustomobject]@{
        Status      = $status
        Body        = $detail
        IntakeError = $intakeError
    }
}

function New-BobiverseIntakePayload {
    $idem = $IdempotencyKey
    if (-not $idem) {
        $raw = ('{0}|{1}|{2}|{3}' -f $Kind, $Repo, $titleTrim, $Body)
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
    # FR #3318: resolve skill_book (mirrors intake PRODUCT_DEFAULT_SKILL_BOOK /
    # Invoke-BobiverseHarvest product defaults). Explicit -Book wins.
    $bookName = if ($Book -and $Book.Trim()) { $Book.Trim() } else { '' }
    if (-not $bookName) {
        if ($Repo -match '(?i)^SimonBarnett/skills-visionary$') {
            $bookName = 'harvest-skills-visionary'
        }
        elseif ($Repo -match '(?i)^SimonBarnett/a-search$') {
            $bookName = 'harvest-agent-skills'
        }
        elseif ($Repo -match '(?i)^SimonBarnett/agentic_fomprep$') {
            $bookName = 'harvest-agent-skills'
        }
        else {
            $bookName = 'harvest'
        }
    }
    return [ordered]@{
        kind             = $Kind
        repo             = $Repo
        title            = $titleTrim
        body             = $Body
        idempotency_key  = $idem
        source           = [ordered]@{
            machine    = ([string]$mach).Substring(0, [Math]::Min(64, ([string]$mach).Length))
            agent      = ([string]$Agent).Substring(0, [Math]::Min(64, ([string]$Agent).Length))
            skill_book = $bookName
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
    $json = ($Payload | ConvertTo-Json -Depth 6 -Compress)
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
    'Content-Type' = 'application/json; charset=utf-8'
}
if ($env:BOB_INTAKE_KEY) {
    $headers['X-Bob-Intake-Key'] = [string]$env:BOB_INTAKE_KEY
}

function Get-IntakeResponseProp {
    # FR #2379: StrictMode - optional intake JSON keys (url / queued) may be absent on 202.
    param($Response, [Parameter(Mandatory)][string]$Name, $Default = $null)
    if ($null -eq $Response) { return $Default }
    $prop = $Response.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

$bodyJson = ($payload | ConvertTo-Json -Depth 6 -Compress)
# FR #611: always POST UTF-8 bytes (WinPS string -Body can be UTF-16 on some hosts).
$bodyBytes = [Text.Encoding]::UTF8.GetBytes($bodyJson)
try {
    $resp = Invoke-RestMethod -Method Post -Uri $IntakeUrl -Headers $headers `
        -Body $bodyBytes -TimeoutSec $TimeoutSec
    return [pscustomobject]@{
        ok              = $true
        queued_local    = $false
        intake_id       = (Get-IntakeResponseProp -Response $resp -Name 'intake_id' -Default $null)
        url             = (Get-IntakeResponseProp -Response $resp -Name 'url' -Default $null)
        queued          = [bool](Get-IntakeResponseProp -Response $resp -Name 'queued' -Default $false)
        idempotency_key = $payload.idempotency_key
        outbox          = @()
        error           = $null
        intake_error    = $null
        http_status     = 202
    }
}
catch {
    $info = Get-BobiverseIntakeErrorDetail -ErrorRecord $_
    $paths = Write-BobiverseIntakeOutbox -Payload $payload -Dirs ($outDirs | Select-Object -Unique)
    $msg = [string]$_.Exception.Message
    if ($info.IntakeError) {
        $msg = "HTTP {0} intake error={1}" -f $(if ($info.Status) { $info.Status } else { '?' }), $info.IntakeError
        if ($info.Body) { $msg = "$msg body=$($info.Body)" }
    }
    elseif ($info.Body) {
        $msg = "$msg body=$($info.Body)"
    }
    return [pscustomobject]@{
        ok              = $false
        queued_local    = $true
        intake_id       = $null
        url             = $null
        queued          = $true
        idempotency_key = $payload.idempotency_key
        outbox          = $paths
        error           = $msg
        intake_error    = $info.IntakeError
        http_status     = $info.Status
    }
}
