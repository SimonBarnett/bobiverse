#Requires -Version 5.1
<#
.SYNOPSIS
  Harvest step for any Bobiverse debugging/maintenance session: file what you learned to the intake webhook.

.DESCRIPTION
  Builds ONE harvest payload (kind=harvest, repo = -Repo / job repo / lesson owner; never a silent bobiverse default) from -Summary / -Lesson /
  optional -SkillFile contents and POSTs it to https://irc.ntsa.uk/bob/v1/intake. No password or token is needed.
  Offline or failing POSTs are written to harvest-outbox/ and resent by -Flush (same idempotency_key, so retries
  never duplicate). Refuses to send anything that looks like a secret. Prints a receipt (intake id) or the queue file.

  Use Report-BobiverseIntakeIssue.ps1 for individual bugs / FRs; use this script to close a session.

.EXAMPLE
  .\Invoke-BobiverseHarvest.ps1 -Summary 'ear restart loop' -Lesson 'Start-Bob must pass --host or the watcher kills the ear'
.EXAMPLE
  .\Invoke-BobiverseHarvest.ps1 -Summary 'MRB lesson' -Lesson 'vision-first before hostile tests' -Book bobiverse-bob-job-mrb
.EXAMPLE
  .\Invoke-BobiverseHarvest.ps1 -Flush
#>
[CmdletBinding()]
param(
    [string]$Summary = '',
    [string[]]$Lesson = @(),
    [string[]]$SkillFile = @(),
    [string]$Repo = '',  # a-search fix: no silent bobiverse default; resolved below (job repo / lesson owner)
    [string]$JobRepo = '',  # FR #3189: offered job owner/name (or BOB_JOB_REPO / run\job-repo.txt)
    [string]$ExistingPrUrl = '',  # FR #1812: when set / already in Summary, intake links PR (no fallback skill issue)
    [string]$Book = 'harvest',  # FR #2705: sets source.skill_book for lesson → SKILL.md routing
    [string]$IntakeUrl = 'https://irc.ntsa.uk/bob/v1/intake',
    [string]$Machine = '',
    [string]$OutboxDir = '',
    [switch]$Flush,
    [switch]$NoDefaultOutboxes,  # FR #139 tests: only flush -OutboxDir
    [switch]$DryRun,
    [int]$TimeoutSec = 30
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$secretRx = '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(password|passwd|secret|token|apikey|api_key)\s*[:=]\s*[A-Za-z0-9/+_.-]{8,}))'
$home1 = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
if (-not $OutboxDir) { $OutboxDir = Join-Path $home1 '.grok\bob\harvest-outbox' }
$headers = @{ 'Content-Type' = 'application/json; charset=utf-8' }
if ($env:BOB_INTAKE_KEY) { $headers['X-Bob-Intake-Key'] = [string]$env:BOB_INTAKE_KEY }

# FR #611: permanent intake validation errors (mirror intake.PERMANENT_INTAKE_ERRORS).
$script:PermanentIntakeErrors = @(
    'malformed', 'bad_kind', 'missing_repo', 'bad_repo', 'repo_not_allowed',
    'bad_title', 'bad_files', 'too_many_files', 'bad_file_path', 'file_too_large',
    'payload_too_large', 'empty_harvest', 'bad_idempotency_key', 'unauthorized', 'worker_receipt_not_issue'
)

function Send-Payload([string]$Json) {
    # Always UTF-8 bytes (WinPS string -Body can be UTF-16 on some hosts).
    $bytes = [Text.Encoding]::UTF8.GetBytes($Json)
    return Invoke-RestMethod -Method Post -Uri $IntakeUrl -Headers $headers -Body $bytes -TimeoutSec $TimeoutSec
}

function Get-IntakeErrorName {
    param($ErrorRecord)
    $detail = ''
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        $detail = [string]$ErrorRecord.ErrorDetails.Message
    }
    if ($detail -match '"error"\s*:\s*"([^"]+)"') {
        return $Matches[1].ToLowerInvariant()
    }
    return ''
}

function Get-IntakeAllowRepos {
    # Historical examples / extra allow (FR #139 / #795 / #3023 / #3050).
    # FR #3135: Flush uses Test-IntakeRepoAllowed (any SimonBarnett/*) first.
    $fallback = @(
        'SimonBarnett/bobiverse',
        'SimonBarnett/skills-visionary',
        'SimonBarnett/agentic_fomprep',
        'SimonBarnett/a-search',  # FR #3023
        'SimonBarnett/trutex'  # FR #3050
    )
    $candidates = @(
        (Join-Path $PSScriptRoot 'intake.py'),
        (Join-Path (Split-Path $PSScriptRoot -Parent) 'common\scripts\intake.py')
    )
    foreach ($p in $candidates) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $t = Get-Content -LiteralPath $p -Raw -Encoding UTF8
        $m = [regex]::Match($t, 'DEFAULT_ALLOW_REPOS\s*=\s*frozenset\(\s*\{(?<body>.*?)\}', [Text.RegularExpressions.RegexOptions]::Singleline)
        if (-not $m.Success) { continue }
        $repos = @(
            [regex]::Matches($m.Groups['body'].Value, '"([^"]+)"') | ForEach-Object { $_.Groups[1].Value }
        )
        if ($repos.Count -gt 0) { return $repos }
    }
    return $fallback
}

function Test-IntakeRepoAllowed {
    # FR #3135: mirror intake.repo_allowed — any SimonBarnett/<name>, else DEFAULT_ALLOW_REPOS.
    param([Parameter(Mandatory)][string]$Repo)
    $r = ($Repo -as [string]).Trim()
    if (-not $r) { return $false }
    if ($r -match '^(?i)SimonBarnett/[A-Za-z0-9_.-]+$') { return $true }
    $allow = @(Get-IntakeAllowRepos | ForEach-Object { $_.ToLowerInvariant() })
    return $allow -contains $r.ToLowerInvariant()
}

function Get-IntakeResponseProp {
    # FR #2379: StrictMode — optional intake JSON keys (url / queued) may be absent on 202.
    param($Response, [Parameter(Mandatory)][string]$Name, $Default = $null)
    if ($null -eq $Response) { return $Default }
    $prop = $Response.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Get-IntakeHttpStatus {
    param($ErrorRecord)
    $ex = $ErrorRecord.Exception
    while ($null -ne $ex) {
        # FR #1842: StrictMode — only touch .Response when the property exists.
        $respProp = $ex.PSObject.Properties['Response']
        if ($null -ne $respProp -and $null -ne $respProp.Value) {
            $resp = $respProp.Value
            $codeProp = $resp.PSObject.Properties['StatusCode']
            if ($null -ne $codeProp -and $null -ne $codeProp.Value) {
                try { return [int]$codeProp.Value } catch { }
                try { return [int]$codeProp.Value.value__ } catch { }
            }
        }
        $ex = $ex.InnerException
    }
    $detail = ''
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        $detail = [string]$ErrorRecord.ErrorDetails.Message
    }
    if ($detail -match '"error"\s*:\s*"repo_not_allowed"' -or $detail -match 'repo_not_allowed') {
        return 403
    }
    if ($ErrorRecord.Exception.Message -match '\(403\)') { return 403 }
    if ($ErrorRecord.Exception.Message -match '\(400\)') { return 400 }
    if ($ErrorRecord.Exception.Message -match '\(401\)') { return 401 }
    if ($detail -match '"error"\s*:\s*"(bad_title|bad_kind|payload_too_large|malformed)"') {
        return 400
    }
    return $null
}

function Move-OutboxDropped {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Reason)
    # FR #1910: concurrent Flush may have already removed/moved the source — treat as success.
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "DROPPED $Path (already gone; $Reason)"
        return
    }
    $dir = Split-Path -Parent $Path
    $dropDir = Join-Path $dir 'dropped'
    New-Item -ItemType Directory -Force -Path $dropDir | Out-Null
    $dest = Join-Path $dropDir (Split-Path -Leaf $Path)
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
    try {
        Move-Item -LiteralPath $Path -Destination $dest -Force
        Write-Host "DROPPED $Path -> $dest ($Reason)"
    } catch {
        if (-not (Test-Path -LiteralPath $Path)) {
            Write-Host "DROPPED $Path (race; already gone; $Reason)"
            return
        }
        throw
    }
}

if ($Flush) {
    if ($NoDefaultOutboxes) {
        if (-not $OutboxDir) { throw '-NoDefaultOutboxes requires -OutboxDir' }
        $dirs = @($OutboxDir)
    } else {
        $dirs = @(
            $OutboxDir,
            (Join-Path (Get-Location).Path 'harvest-outbox'),
            (Join-Path (Get-Location).Path 'report-outbox'),
            (Join-Path $home1 '.grok\bob\report-outbox'),
            (Join-Path $home1 '.grok\bob\harvest-outbox')
        ) | Select-Object -Unique
    }
    $sent = 0; $kept = 0; $dropped = 0
    foreach ($d in $dirs) {
        if (-not (Test-Path -LiteralPath $d)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $d -File -Filter '*.json' -ErrorAction SilentlyContinue)) {
            $raw = $null
            $payload = $null
            try {
                $raw = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8
                $payload = $raw | ConvertFrom-Json
            } catch {
                Move-OutboxDropped -Path $f.FullName -Reason 'malformed_json'
                $dropped++
                continue
            }
            $repo = ''
            if ($payload -and $payload.PSObject.Properties.Name -contains 'repo') {
                $repo = [string]$payload.repo
            }
            if (-not $repo) {
                Move-OutboxDropped -Path $f.FullName -Reason 'missing_repo'
                $dropped++
                continue
            }
            if (-not (Test-IntakeRepoAllowed -Repo $repo)) {
                # FR #139 / #3135: never retry non-SimonBarnett (and non-extra-allow) repos.
                Move-OutboxDropped -Path $f.FullName -Reason ("repo_not_allowed:$repo")
                $dropped++
                continue
            }
            # FR #611: drop locally if title/kind already permanently invalid.
            $title = ''
            if ($payload.PSObject.Properties.Name -contains 'title') { $title = [string]$payload.title }
            $kind = 'issue'
            if ($payload.PSObject.Properties.Name -contains 'kind') {
                $k = [string]$payload.kind
                if ($k) { $kind = $k.ToLowerInvariant() }
            }
            if (-not $title.Trim() -or $title.Trim().Length -gt 200) {
                Move-OutboxDropped -Path $f.FullName -Reason 'bad_title'
                $dropped++
                continue
            }
            if (@('issue', 'fr', 'skill', 'harvest') -notcontains $kind) {
                Move-OutboxDropped -Path $f.FullName -Reason 'bad_kind'
                $dropped++
                continue
            }
            try {
                $r = Send-Payload $raw
                # FR #1910: another Flush may have archived the file after SENT — do not fail the cycle.
                if (Test-Path -LiteralPath $f.FullName) {
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
                }
                $sent++
                Write-Host ("SENT {0} intake_id={1}" -f $f.Name, (Get-IntakeResponseProp -Response $r -Name 'intake_id' -Default ''))
            } catch {
                $status = Get-IntakeHttpStatus -ErrorRecord $_
                $intakeErr = Get-IntakeErrorName -ErrorRecord $_
                $msg = [string]$_.Exception.Message
                if ($intakeErr) { $msg = "HTTP $status intake error=$intakeErr ($msg)" }
                $permanent = $false
                if ($status -eq 403 -or $msg -match 'repo_not_allowed' -or $intakeErr -eq 'repo_not_allowed') {
                    Move-OutboxDropped -Path $f.FullName -Reason 'http_403_repo_not_allowed'
                    $dropped++
                    $permanent = $true
                }
                elseif ($intakeErr -and ($script:PermanentIntakeErrors -contains $intakeErr)) {
                    Move-OutboxDropped -Path $f.FullName -Reason ("http_{0}_{1}" -f $(if ($status) { $status } else { 400 }), $intakeErr)
                    $dropped++
                    $permanent = $true
                }
                elseif ($status -eq 400) {
                    # FR #611: bare 400 without body still permanent (validation); do not retry forever.
                    Move-OutboxDropped -Path $f.FullName -Reason 'http_400'
                    $dropped++
                    $permanent = $true
                }
                if (-not $permanent) {
                    $kept++
                    Write-Host "KEPT $($f.FullName): $msg"
                }
            }
        }
    }
    Write-Host "flush: sent=$sent kept=$kept dropped=$dropped"
    return
}

if (-not $Summary.Trim()) { throw '-Summary is required (what broke / what you fixed / "nothing new")' }

# FR #3189: harvest repo keys on the job's product repo (a-search → SimonBarnett/a-search).
# Explicit -Repo wins; else -JobRepo, else BOB_JOB_REPO, else run\job-repo.txt beside BOB_OUTBOX.
$script:ExplicitRepo = $PSBoundParameters.ContainsKey('Repo')
if (-not $JobRepo -or -not $JobRepo.Trim()) {
    if ($env:BOB_JOB_REPO -and ([string]$env:BOB_JOB_REPO).Trim()) {
        $JobRepo = ([string]$env:BOB_JOB_REPO).Trim()
    } elseif ($env:BOB_OUTBOX -and ([string]$env:BOB_OUTBOX).Trim()) {
        try {
            $marker = Join-Path (Split-Path -Parent ([string]$env:BOB_OUTBOX)) 'job-repo.txt'
            if (Test-Path -LiteralPath $marker) {
                $JobRepo = ((Get-Content -LiteralPath $marker -TotalCount 1 -ErrorAction SilentlyContinue) -as [string]).Trim()
            }
        } catch { }
    }
}
# a-search fix: job keys arrive typed ("FR SimonBarnett/a-search#637") or with "#N"; normalise.
if ($JobRepo) {
    $JobRepo = ([string]$JobRepo).Trim()
    $JobRepo = $JobRepo -replace '(?i)^\s*(?:(?:ACK|DONE|NACK|GIVEUP)\s+)?(?:FR|MRB|UAT)\s+', ''
    $JobRepo = ($JobRepo -replace '\s*#\s*\d+.*$', '').Trim()
}
if (-not $script:ExplicitRepo -and $JobRepo -and ($JobRepo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) {
    $Repo = $JobRepo.Trim()
}
# a-search fix: never fall back to bobiverse silently. No job repo -> the product named in
# the lesson owns it (a-search, agentic_fomprep, skills-visionary); Bob tooling -> bobiverse;
# a worker seat with neither must pass -Repo (throw so the agent retries with the job repo).
if (-not $Repo -or -not $Repo.Trim()) {
    $ownerBlob = ($Summary + "`n" + (($Lesson | ForEach-Object { $_ }) -join "`n"))
    $bobCue = ($ownerBlob -match '(?i)bob-worker|_release_gen|release_gen|done-miss|boredemitter|fleet-ops|hotpatch|\b(jeeves|ircjeeves|bob-tray|tipform|chair outbox|intake allowlist|gitclaim|airc)\b')
    if ($ownerBlob -match '(?i)\bSimonBarnett/a-search\b|\ba-search\b') {
        $Repo = 'SimonBarnett/a-search'
    } elseif ($ownerBlob -match '(?i)\bagentic_fomprep\b') {
        $Repo = 'SimonBarnett/agentic_fomprep'
    } elseif ($ownerBlob -match '(?i)\bskills-visionary\b') {
        $Repo = 'SimonBarnett/skills-visionary'
    } elseif ($bobCue -or -not ($env:BOB_OUTBOX -and ([string]$env:BOB_OUTBOX).Trim())) {
        $Repo = 'SimonBarnett/bobiverse'
    } else {
        throw "harvest repo unknown: pass -Repo <owner/repo of the job you worked> (e.g. -Repo SimonBarnett/a-search). Never default product lessons to SimonBarnett/bobiverse."
    }
    Write-Host "INFO harvest repo inferred: $Repo (pass -Repo to be explicit)"
}

if (-not ($Repo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) { throw "Repo must be owner/name (got '$Repo')" }
if (-not $Machine) { $Machine = if ($env:BOB_MACHINE_ID) { [string]$env:BOB_MACHINE_ID } else { [string]$env:COMPUTERNAME } }

# FR #936: do not file harvest skill issues for GIVEUP-of-skill sessions — live chair
# (pre-recompose) re-offers them as FR and each GIVEUP+harvest creates another skill issue.
function Test-HarvestSkillGiveupLoop([string]$SummaryText, [string[]]$LessonLines) {
    $s = [string]$SummaryText
    $joined = (@($s) + @($LessonLines)) -join "`n"
    if ($s -match '(?i)^\s*GIVEUP\b' -and $joined -match '(?i)\bskill(\s|-)?(labeled\s+)?harvest\b') {
        return $true
    }
    if ($s -match '(?i)skill\s+harvest' -and $s -match '(?i)\bGIVEUP\b') {
        return $true
    }
    if ($joined -match '(?i)Harvest-of-harvest skill issues offered as FR') {
        return $true
    }
    return $false
}

# FR #2237: twin/already-fixed DONE harvests that only restate Duplicate-of / DONE-citing
# covering-PR playbooks re-enter the FR queue as nested skill twins. Skip filing those.
function Test-HarvestTwinDoneLoop([string]$SummaryText, [string[]]$LessonLines) {
    $s = [string]$SummaryText
    $joined = (@($s) + @($LessonLines)) -join "`n"
    $hasTwin = ($joined -match '(?i)\b(Duplicate of|twin of|nested twin|meta-twin|already[- ]CLOSED|already closed)\b')
    $hasDoneCite = (
        ($joined -match '(?i)\bDONE\b.*\b(citing|cites)\b') -or
        ($joined -match '(?i)\bciting\b.*(#\d+|pull/\d+|PR\s*#?\d+)')
    )
    $hasTwinPlaybook = (
        ($joined -match '(?i)Closed skill-harvest twin') -or
        ($joined -match '(?i)ACK then DONE citing covering PR') -or
        ($joined -match '(?i)close as Duplicate of #?N') -or
        ($joined -match '(?i)never open a second promote') -or
        ($joined -match '(?i)one issue per issue')
    )
    if ($hasTwin -and ($hasDoneCite -or $hasTwinPlaybook)) {
        return $true
    }
    if ($hasTwinPlaybook -and ($hasTwin -or $hasDoneCite)) {
        return $true
    }
    return $false
}

if (Test-HarvestSkillGiveupLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest skill GIVEUP loop (FR #936): not filing GitHub skill issue for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}
if (Test-HarvestTwinDoneLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest twin-DONE loop (FR #2237): not filing GitHub skill issue for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

# FR #2970: FAIL-supersede / wrong-book Harvest-lesson MRB *process* playbooks belong in
# bobiverse-bob-job-mrb. Re-harvesting them with default -Book harvest opens twin lesson(harvest)
# tips that the next MRB FAIL-supersedes again. Skip client-side (intake also gates).
# FR #2991: also skip thin already-covered twins (FAIL-supersede + already cover / close thin
# twins / citing product PRs) that lack job-mrb process cues — same class as tip #2990.
function Test-HarvestFailSupersedeProcessLoop([string]$SummaryText, [string[]]$LessonLines) {
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    $isFailSuper = ($joined -match '(?i)FAIL[- ]supersede')
    $isProcess = (
        ($joined -match '(?i)belong(?:s)? in\s+`?bobiverse-bob-job-mrb') -or
        ($joined -match '(?i)docs/mrb-N after skill merge') -or
        ($joined -match '(?i)Harvest-lesson MRB:\s*process') -or
        ($joined -match '(?i)never merge a second copy') -or
        ($joined -match '(?i)wrong[- ]book') -or
        ($joined -match '(?i)process playbooks?')
    )
    $isThinTwin = (
        ($joined -match '(?i)already\s+cover(?:s|ed)?') -or
        ($joined -match '(?i)close\s+thin\b') -or
        ($joined -match '(?i)thin\s+harvest(?:ed)?[- ]?lessons?\b') -or
        ($joined -match '(?i)thin\s+harvest\s+twin') -or
        ($joined -match '(?i)Harvested-lessons\s+intake\s+twins?') -or
        ($joined -match '(?i)citing\s+(?:the\s+)?product(?:/move)?\s*PRs?')
    )
    if ($isFailSuper -and $isProcess) { return $true }
    if ($isProcess -and ($joined -match '(?i)park(?:ed|s)?\s+under\s+harvest')) { return $true }
    if ($isFailSuper -and $isThinTwin) { return $true }  # FR #2991
    return $false
}
if (Test-HarvestFailSupersedeProcessLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest FAIL-supersede process loop (FR #2970/#2991): not filing lesson(harvest) for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

$files = @()
foreach ($sf in $SkillFile) {
    if (-not (Test-Path -LiteralPath $sf)) { throw "skill file not found: $sf" }
    $item = Get-Item -LiteralPath $sf
    if ($item.Length -gt 100KB) { throw "skill file too large (max 100 KB): $sf" }
    $files += [ordered]@{ path = ('harvest/' + $item.Name); content = (Get-Content -LiteralPath $sf -Raw -Encoding UTF8) }
}
$lessonText = if ($Lesson.Count) { ($Lesson | ForEach-Object { '- ' + $_ }) -join "`n" } else { '- (no new playbook line)' }
$body = "Session summary:`n$Summary`n`nLessons:`n$lessonText`n"
$scan = $body + (($files | ForEach-Object { $_.content }) -join "`n")
if ($scan -match $secretRx) { throw 'refusing to send: text looks like it contains a secret/token/password. Remove it and retry.' }

if ($ExistingPrUrl) {
    $eu = $ExistingPrUrl.Trim()
    if ($eu -and $body -notmatch [regex]::Escape($eu)) {
        $body = $body + "`nExisting PR: $eu`n"
    }
}
$title = 'harvest: ' + $Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length))

# FR #1812: when -Summary/-Lesson already cite https://github.com/.../pull/N (or pass -ExistingPrUrl), intake links that PR and does not file a fallback skill issue.
# FR #2705: -Book sets source.skill_book so Lessons land in that SKILL.md (default harvest).
$bookName = if ($Book -and $Book.Trim()) { $Book.Trim() } else { 'harvest' }
$bookName = $bookName.Substring(0, [Math]::Min(64, $bookName.Length))
$inferBlob = (($Summary + "`n" + (($Lesson | ForEach-Object { $_ }) -join "`n"))).ToLowerInvariant()
$script:ExplicitBook = $PSBoundParameters.ContainsKey('Book')
# FR #3004: default harvest yields to an inferred product book from Summary+Lesson cues
# (mirrors intake resolve_skill_book soft override) so bob-worker playbooks are not
# re-opened as lesson(harvest) when the owning skill already has the bullet.
if ($bookName -eq 'harvest') {
    # Strong product cues only — bare "MRB"/"UAT" in session summaries must not re-route.
    if ($inferBlob -match 'bob-worker|_release_gen|release_gen|done-miss|boredemitter') {
        $bookName = 'bobiverse-bob-worker'
        Write-Host "INFO FR #3004 inferred skill_book=bobiverse-bob-worker from Summary/Lesson cues"
    } elseif ($inferBlob -match 'fleet-ops|hotpatch') {
        $bookName = 'bobiverse-fleet-ops'
        Write-Host "INFO FR #3004 inferred skill_book=bobiverse-fleet-ops from Summary/Lesson cues"
    }
}
# FR #3189 split: Bob tooling (worker/fleet/chair/tray/intake process) stays on bobiverse
# even when the seat's job row is a product repo. Product playbooks keep the job repo.
$bobTooling = (
    ($bookName -match '^bobiverse-') -or
    ($inferBlob -match 'bob-worker|_release_gen|release_gen|done-miss|boredemitter|fleet-ops|hotpatch') -or
    ($inferBlob -match '(?i)\b(jeeves|ircjeeves|bob-tray|tipform|chair outbox|intake allowlist)\b')
)
if ($bobTooling -and -not $script:ExplicitRepo) {
    if ($Repo -notmatch '(?i)^SimonBarnett/bobiverse$') {
        Write-Host "INFO FR #3189 split: Bob tooling lesson -> repo=SimonBarnett/bobiverse (was $Repo)"
    }
    $Repo = 'SimonBarnett/bobiverse'
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/a-search$')) {
    $bookName = 'harvest-agent-skills'
    Write-Host "INFO FR #3189 product default skill_book=harvest-agent-skills for SimonBarnett/a-search"
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/skills-visionary$')) {
    $bookName = 'harvest-skills-visionary'
    Write-Host "INFO FR #3317 product default skill_book=harvest-skills-visionary for SimonBarnett/skills-visionary"
}

# FR #3317: DryRun (and payload) emit the owning skill-book path inside that repo.
$skillBookPath = ''
switch -Regex ($bookName) {
    '^harvest-agent-skills$' {
        if ($Repo -match '(?i)^SimonBarnett/bobiverse$') {
            $skillBookPath = 'common/.grok/skills/harvest-agent-skills/SKILL.md'
        } else {
            $skillBookPath = '.grok/skills/harvest-agent-skills/SKILL.md'
        }
    }
    '^harvest-skills-visionary$' { $skillBookPath = '.grok/skills/harvest-skills-visionary/SKILL.md' }
    '^harvest$' { $skillBookPath = 'common/.grok/skills/harvest/SKILL.md' }
    '^bobiverse-bob-worker$' { $skillBookPath = 'bob/.grok/skills/bobiverse-bob-worker/SKILL.md' }
    '^bobiverse-fleet-ops$' { $skillBookPath = 'common/.grok/skills/bobiverse-fleet-ops/SKILL.md' }
    '^bobiverse-bob-job-mrb$' { $skillBookPath = 'bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md' }
    '^bobiverse-bob-job-irc$' { $skillBookPath = 'bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md' }
    '^bobiverse-bob-job-fr$' { $skillBookPath = 'bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md' }
    '^bobiverse-bob-job-uat$' { $skillBookPath = 'bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md' }
    '^bobiverse-jeeves' { $skillBookPath = "jeeves/.grok/skills/$bookName/SKILL.md" }
    '^bobiverse-airc' { $skillBookPath = "airc/.grok/skills/$bookName/SKILL.md" }
    '^bobiverse-' { $skillBookPath = "bob/.grok/skills/$bookName/SKILL.md" }
    default {
        if ($Repo -match '(?i)^SimonBarnett/bobiverse$') {
            $skillBookPath = "common/.grok/skills/$bookName/SKILL.md"
        } else {
            $skillBookPath = ".grok/skills/$bookName/SKILL.md"
        }
    }
}

$sha = [Security.Cryptography.SHA256]::Create()
$idem = 'hv-' + ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes("$Repo|$title|$body"))) -replace '-', '').Substring(0, 24).ToLowerInvariant()
# FR #2790: bob-worker seats export BOB_NICK (and BOB_AGENT_NICK alias); prefer BOB_NICK
# so lesson PR footers carry seat=<nick> for Jeeves self-MRB blocking. Fall back to
# BOB_AGENT_NICK for Watch-AgentHealth / legacy seats that only set that name.
$seatNick = ''
if ($env:BOB_NICK -and ([string]$env:BOB_NICK).Trim()) {
    $seatNick = ([string]$env:BOB_NICK).Trim()
} elseif ($env:BOB_AGENT_NICK -and ([string]$env:BOB_AGENT_NICK).Trim()) {
    $seatNick = ([string]$env:BOB_AGENT_NICK).Trim()
}
if ($seatNick.Length -gt 64) { $seatNick = $seatNick.Substring(0, 64) }
$payload = [ordered]@{
    kind = 'harvest'; repo = $Repo; title = $title; body = $body; idempotency_key = $idem
    skill_book_path = $skillBookPath
    source = [ordered]@{ machine = $Machine.Substring(0, [Math]::Min(64, $Machine.Length)); agent = 'Invoke-BobiverseHarvest'; skill_book = $bookName; skill_book_path = $skillBookPath; version = ''; seat = $seatNick }
}
if ($files.Count) { $payload.files = $files }
$json = $payload | ConvertTo-Json -Depth 6
if ($DryRun) {
    Write-Host ("INFO FR #3317 DryRun repo={0} skill_book={1} skill_book_path={2}" -f $Repo, $bookName, $skillBookPath)
    Write-Host $json
    return
}
try {
    $r = Send-Payload $json
    $intakeId = Get-IntakeResponseProp -Response $r -Name 'intake_id' -Default ''
    $url = Get-IntakeResponseProp -Response $r -Name 'url' -Default ''
    $queued = Get-IntakeResponseProp -Response $r -Name 'queued' -Default $false
    Write-Host "HARVESTED intake_id=$intakeId url=$url queued=$queued"
} catch {
    New-Item -ItemType Directory -Force -Path $OutboxDir | Out-Null
    $out = Join-Path $OutboxDir ("harvest-$idem.json")
    [IO.File]::WriteAllText($out, $json + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host "QUEUED $out ($($_.Exception.Message)); resend with: .\scripts\Invoke-BobiverseHarvest.ps1 -Flush"
}
