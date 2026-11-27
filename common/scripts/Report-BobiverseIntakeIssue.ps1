#Requires -Version 4.0
<#
.SYNOPSIS
  POST kind=issue|fr|skill|harvest to https://bob.ntsa.uk/bob/v1/intake (honesty-box / no-gh path).

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
    [string]$IntakeUrl = 'https://bob.ntsa.uk/bob/v1/intake',
    [string]$IdempotencyKey = '',
    [string]$Machine = '',
    [string]$Agent = 'Report-BobiverseIntakeIssue',
    [string]$OutboxDir = '',
    [string]$InstallRoot = '',
    [int]$TimeoutSec = 30,
    # FR #3395: skip HTTP; return the payload shape (tests / installer dry paths).
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# FR #7121: one canonical Priority skill-book repo; agentic_fomprep is an alias.
function ConvertTo-BobiverseCanonicalRepo {
    param([string]$Name)
    if ($Name -match '(?i)^(?:SimonBarnett/)?(?:agentic_fomprep|priority-mcp)$') {
        return 'SimonBarnett/priority-mcp'
    }
    return $Name
}
$Repo = ConvertTo-BobiverseCanonicalRepo $Repo

if (-not ($Repo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) {
    throw "Repo must be owner/name (got '$Repo'). Intake requires an explicit target repo."
}

# FR #3395: defence in depth for airc installer kind=issue reports - honour crash-report opt-out.
$script:BobiverseCrashOptOutSkip = $false
$isAircInstallRoot = $false
if ($InstallRoot -and $InstallRoot.Trim()) {
    $ir = $InstallRoot.Trim()
    $isAircInstallRoot = (
        (Test-Path -LiteralPath (Join-Path $ir 'config\airc.json')) -or
        (Test-Path -LiteralPath (Join-Path $ir 'config\crash-report.json')) -or
        (Test-Path -LiteralPath (Join-Path $ir 'airc.exe')) -or
        (Test-Path -LiteralPath (Join-Path $ir 'airc\airc.exe'))
    )
}
if ($Kind -eq 'issue' -and $isAircInstallRoot) {
    # MRB #3440: fail closed until policy explicitly allows intake.
    $allow = $false
    $commonBeside = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath $commonBeside) {
        try {
            . $commonBeside
            if (Get-Command Test-BobiverseCrashReportAllowsIntake -ErrorAction SilentlyContinue) {
                $allow = [bool](Test-BobiverseCrashReportAllowsIntake -InstallRoot $InstallRoot)
            }
        } catch {
            $allow = $false
        }
    }
    if (-not $allow) {
        $script:BobiverseCrashOptOutSkip = $true
        Write-Host 'SKIPPED intake FR #3395 crash-report opt-out (airc InstallRoot; kind=issue)'
        try {
            if (Get-Command Write-BobiverseMsiInstallLog -ErrorAction SilentlyContinue) {
                Write-BobiverseMsiInstallLog -Product airc -Message ("intake-skipped-opt-out title={0}" -f $Title)
            }
        } catch { }
    }
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
        elseif ($Repo -match '(?i)^SimonBarnett/(agentic_fomprep|priority-mcp)$') {
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
        [IO.File]::WriteAllText($path, $json + "`n", (New-Object System.Text.UTF8Encoding $false))
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

function Resolve-IntakeIssueNumber {
    # FR #9837: validated positive [int] issue number, or $null. Never use -match/$Matches.
    param(
        $Response,
        [Parameter(Mandatory)][string]$RepoName,
        [bool]$Queued = $false
    )
    if ($Queued) { return $null }
    $rawNum = Get-IntakeResponseProp -Response $Response -Name 'number' -Default $null
    $rawUrl = Get-IntakeResponseProp -Response $Response -Name 'url' -Default $null
    $num = $null
    if ($null -ne $rawNum -and "$rawNum" -ne '') {
        $s = ("$rawNum").Trim()
        $nm = [regex]::Match($s, '^[0-9]+$')
        if ($nm.Success) {
            $n = [int]$s
            if ($n -gt 0) { $num = $n }
        }
    }
    $urlNum = $null
    $urlText = if ($null -eq $rawUrl) { '' } else { ("$rawUrl").Trim() }
    if ($urlText -ne '') {
        $escaped = [regex]::Escape($RepoName)
        $pat = ('(?i)^https://github\.com/{0}/issues/([0-9]+)/?$' -f $escaped)
        $m = [regex]::Match($urlText, $pat)
        if ($m.Success) {
            $u = [int]$m.Groups[1].Value
            if ($u -gt 0) { $urlNum = $u }
        }
    }
    if ($null -ne $num -and $null -ne $urlNum) {
        if ($num -eq $urlNum) { return $num }
        return $null
    }
    if ($null -ne $num -and $urlText -eq '') { return $num }
    if ($null -eq $num -and $null -ne $urlNum) { return $urlNum }
    return $null
}

if ($script:BobiverseCrashOptOutSkip) {
    return [pscustomobject]@{
        ok                     = $true
        queued_local           = $false
        skipped_crash_opt_out  = $true
        dry_run                = $false
        intake_id              = $null
        url                    = $null
        queued                 = $false
        repo                   = $Repo
        idempotency_key        = $payload.idempotency_key
        outbox                 = @()
        error                  = $null
        intake_error           = $null
        http_status            = $null
        number                 = $null
        action                 = $null
    }
}

if ($DryRun) {
    Write-Host ("DRYRUN Report-BobiverseIntakeIssue repo={0} kind={1} title={2}" -f $Repo, $Kind, $titleTrim)
    return [pscustomobject]@{
        ok                     = $true
        queued_local           = $false
        skipped_crash_opt_out  = $false
        dry_run                = $true
        intake_id              = $null
        url                    = $null
        queued                 = $false
        repo                   = $Repo
        idempotency_key        = $payload.idempotency_key
        outbox                 = @()
        error                  = $null
        intake_error           = $null
        http_status            = $null
        number                 = $null
        action                 = $null
    }
}

$bodyJson = ($payload | ConvertTo-Json -Depth 6 -Compress)
# FR #611: always POST UTF-8 bytes (WinPS string -Body can be UTF-16 on some hosts).
$bodyBytes = [Text.Encoding]::UTF8.GetBytes($bodyJson)
try {
    $resp = Invoke-RestMethod -Method Post -Uri $IntakeUrl -Headers $headers `
        -Body $bodyBytes -TimeoutSec $TimeoutSec
    $queuedFlag = [bool](Get-IntakeResponseProp -Response $resp -Name 'queued' -Default $false)
    $issueUrl = Get-IntakeResponseProp -Response $resp -Name 'url' -Default $null
    $intakeId = Get-IntakeResponseProp -Response $resp -Name 'intake_id' -Default $null
    $issueNumber = Resolve-IntakeIssueNumber -Response $resp -RepoName $Repo -Queued $queuedFlag
    $issueAction = Get-IntakeResponseProp -Response $resp -Name 'action' -Default $null
    if ($null -ne $issueAction) { $issueAction = [string]$issueAction }
    # FR #9837: host-stream lines for process callers; do not Write-Output (keeps single pipeline object).
    if ($null -ne $issueNumber) {
        $urlForHost = if ($null -eq $issueUrl) { '' } else { ("$issueUrl").Trim() }
        if ($urlForHost -ne '') {
            Write-Host ("ISSUE_URL={0}" -f $urlForHost)
        }
        Write-Host ("ISSUE_NUMBER={0}" -f $issueNumber)
    }
    else {
        Write-Host ("ISSUE_PENDING intake_id={0} queued={1}" -f $intakeId, $queuedFlag)
    }
    return [pscustomobject]@{
        ok              = $true
        queued_local    = $false
        intake_id       = $intakeId
        url             = $issueUrl
        queued          = $queuedFlag
        idempotency_key = $payload.idempotency_key
        outbox          = @()
        error           = $null
        intake_error    = $null
        http_status     = 202
        number          = $issueNumber
        action          = $issueAction
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
        number          = $null
        action          = $null
    }
}
