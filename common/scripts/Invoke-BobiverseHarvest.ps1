#Requires -Version 5.1
<#
.SYNOPSIS
  Harvest step for any Bobiverse debugging/maintenance session: file what you learned to the intake webhook.

.DESCRIPTION
  Builds ONE harvest payload (kind=harvest, repo = -Repo / job repo / lesson owner; never a silent bobiverse default) from -Summary / -Lesson /
  optional -SkillFile contents and POSTs it to https://bob.ntsa.uk/bob/v1/intake. FR #4288: -ExistingPrUrl (or a pull URL in Summary/Lesson) fail-closes tip filing (linked; no second lesson PR). FR #4986: skip/empty/(no new playbook) Lesson never opens a tip. FR #4780: MRB/review of a harvest-lesson tip must not open another lesson tip (lesson-review meta + 24h dedup). FR #4917: FIX/MRB/re-DONE on lesson or docs/mrb pin PRs skip tip filing (PR metadata + job kind); source.version stamps HARVEST_SCRIPT_VERSION. Product -Repo harvest-agent-skills without ExistingPrUrl stays (FR #3189). No password or token is needed.
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
    [string]$Book = 'harvest',  # FR #2705: sets source.skill_book for lesson -> SKILL.md routing
    [string]$IntakeUrl = 'https://bob.ntsa.uk/bob/v1/intake',
    [string]$Machine = '',
    [string]$OutboxDir = '',
    [switch]$Flush,
    [switch]$NoDefaultOutboxes,  # FR #139 tests: only flush -OutboxDir
    [switch]$DryRun,
    [switch]$NoCitedPrLookup,  # FR #5109: tests / offline --- skip live gh pr view
    [int]$TimeoutSec = 30
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# FR #4917: stamp every harvest receipt (source.version); refuse when seat min is newer.
# HARVEST_SCRIPT_VERSION constant name kept for pin tests / operator greps.
$HARVEST_SCRIPT_VERSION = '20261026-fr4986'
$script:HarvestScriptVersion = $HARVEST_SCRIPT_VERSION
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
        'SimonBarnett/trutex',  # FR #3050
        'SimonBarnett/ce-priority'  # FR #4830
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
    # FR #3135: mirror intake.repo_allowed - any SimonBarnett/<name>, else DEFAULT_ALLOW_REPOS.
    param([Parameter(Mandatory)][string]$Repo)
    $r = ($Repo -as [string]).Trim()
    if (-not $r) { return $false }
    if ($r -match '^(?i)SimonBarnett/[A-Za-z0-9_.-]+$') { return $true }
    $allow = @(Get-IntakeAllowRepos | ForEach-Object { $_.ToLowerInvariant() })
    return $allow -contains $r.ToLowerInvariant()
}

function Get-IntakeResponseProp {
    # FR #2379: StrictMode - optional intake JSON keys (url / queued) may be absent on 202.
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
        # FR #1842: StrictMode - only touch .Response when the property exists.
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
    # FR #1910: concurrent Flush may have already removed/moved the source - treat as success.
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
                # FR #1910: another Flush may have archived the file after SENT - do not fail the cycle.
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

# FR #4917: refuse stale seat overlays that predate the lesson-loop skip (default min = this tip).
$minVer = ([string]$env:BOB_HARVEST_MIN_VER).Trim()
if (-not $minVer) { $minVer = '20261020-fr4780' }
if ($script:HarvestScriptVersion -lt $minVer) {
    throw ("harvest script version {0} older than required {1}; refresh install-tree Invoke-BobiverseHarvest.ps1 (FR #4917 / #4780)" -f $script:HarvestScriptVersion, $minVer)
}

# FR #3189: harvest repo keys on the job's product repo (a-search -> SimonBarnett/a-search).
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
    } elseif ($ownerBlob -match '(?i)\bce-priority\b|\bce-dayworks\b|\bdayworks-launcher\b') {
        $Repo = 'SimonBarnett/ce-priority'
    } elseif ($bobCue -or -not ($env:BOB_OUTBOX -and ([string]$env:BOB_OUTBOX).Trim())) {
        $Repo = 'SimonBarnett/bobiverse'
    } else {
        throw "harvest repo unknown: pass -Repo <owner/repo of the job you worked> (e.g. -Repo SimonBarnett/a-search). Never default product lessons to SimonBarnett/bobiverse."
    }
    Write-Host "INFO harvest repo inferred: $Repo (pass -Repo to be explicit)"
}

if (-not ($Repo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) { throw "Repo must be owner/name (got '$Repo')" }
if (-not $Machine) { $Machine = if ($env:BOB_MACHINE_ID) { [string]$env:BOB_MACHINE_ID } else { [string]$env:COMPUTERNAME } }

# FR #936: do not file harvest skill issues for GIVEUP-of-skill sessions - live chair
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

# FR #4986: bare skip / empty / (no new playbook line) is not a playbook tip
# (class of euroflo#24 lesson(harvest): skip after MRB Duplicate disposition).
function Test-HarvestNoopOrEmptyLesson([string[]]$LessonLines) {
    $lines = @($LessonLines | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
    if (-not $lines.Count) { return $true }
    foreach ($L in $lines) {
        if ($L -notmatch '(?i)^\(?\s*(?:no new playbook line|skip|none|n/?a|noop|nothing|no lessons?)\s*\)?$') {
            return $false
        }
    }
    return $true
}
if (Test-HarvestNoopOrEmptyLesson -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest noop/empty lesson (FR #4986): not filing lesson tip when Lesson is skip/empty/placeholder for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
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
# twins / citing product PRs) that lack job-mrb process cues - same class as tip #2990.
# FR #4176: also skip CLOSED wrong-book / DONE PASS FR #3317 process-loop closeouts that
# lack the FAIL-supersede token (class of tip #4175 after #4171/#4173/#4174).
# FR #4207: also match 'already in (bobiverse-)?job-mrb' and bare 'FR #2970' with FAIL-supersede
# (class of tip #4206; flat/outdated compose missed FR #4176 process-loop cue).
# FR #4231: also skip tip-loop meta / only-restate Thin FAIL-supersede already-on-main
# closeouts for any -Book (class of a-search#1839 under Book=harvest-agent-skills).
# FR #4308: also skip thinner tip + durable lesson already on main (a-search#1980/#2283).
# FR #4484: also skip FAIL-supersede next to "restates main" / "admit main already has"
# (class of a-search#3470; those phrases are not already-on-main / second-copy / job-mrb).
function Test-HarvestFailSupersedeProcessLoop([string]$SummaryText, [string[]]$LessonLines) {
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    $isFailSuper = ($joined -match '(?i)FAIL[- ]supersede')
    $isProcess = (
        ($joined -match '(?i)belong(?:s)? in\s+`?bobiverse-bob-job-mrb') -or
        # FR #3827: tip #3826 used "stay in" / "durable in" instead of "belong(s) in"
        ($joined -match '(?i)(?:stay|durable)\s+in\s+`?bobiverse-bob-job-mrb') -or
        # FR #3959 / #3957: tip #3958 used "durable home is bobiverse-bob-job-mrb"
        ($joined -match '(?i)durable\s+home\s+is\s+`?bobiverse-bob-job-mrb') -or
        # FR #4207: tip #4206 used "already in job-mrb" (short form, no belong/stay/durable)
        ($joined -match '(?i)already\s+in\s+(?:bobiverse-)?job-mrb') -or
        # FR #4207: citing FR #2970 with FAIL-supersede is itself a process-loop closeout
        ($joined -match '(?i)(?:FR\s*#?\s*)?2970') -or
        ($joined -match '(?i)docs/mrb-N after skill merge') -or
        ($joined -match '(?i)Harvest-lesson MRB:\s*process') -or
        ($joined -match '(?i)never merge a second copy') -or
        ($joined -match '(?i)(?:do not|never)\s+(?:append|merge|land)\s+a\s+second\s+copy') -or
        ($joined -match '(?i)second\s+copy\s+under\s+harvest') -or
        ($joined -match '(?i)wrong[- ]book') -or
        ($joined -match '(?i)process playbooks?') -or
        ($joined -match '(?i)restatement playbooks?') -or
        # FR #3959: "do not park FR #3948 ... under harvest/SKILL.md" (words between)
        ($joined -match '(?i)(?:do not|never)\s+park\b[\s\S]{0,120}?under\s+(?:`?harvest|harvest/SKILL)')
    )
    $isThinTwin = (
        ($joined -match '(?i)already\s+cover(?:s|ed)?') -or
        ($joined -match '(?i)already\s+CAST\s+IRON') -or
        # FR #3959: "CAST IRON already on main" (flipped order)
        ($joined -match '(?i)CAST\s+IRON\s+already') -or
        ($joined -match '(?i)close\s+thin\b') -or
        ($joined -match '(?i)thin\s+harvest(?:ed)?[- ]?lessons?\b') -or
        ($joined -match '(?i)thin\s+harvest\s+twin') -or
        # FR #3827: tip #3826 said "thin harvest tip" / restatement
        ($joined -match '(?i)thin\s+harvest\s+(?:tip|restatement)s?\b') -or
        ($joined -match '(?i)Harvested-lessons\s+intake\s+twins?') -or
        ($joined -match '(?i)citing\s+(?:the\s+)?product(?:/move)?\s*PRs?') -or
        # FR #4231: tip-loop meta / only-restate Thin FAIL-supersede already on main
        ($joined -match '(?i)tip[- ]?loop\s+meta') -or
        ($joined -match '(?i)only\s+restate(?:s|ing)?\s+(?:Thin\s+)?FAIL') -or
        ($joined -match '(?i)restate(?:s|ing)?\s+Thin\s+FAIL[- ]supersede') -or
        ($joined -match '(?i)Thin\s+FAIL[- ]supersede[\s\S]{0,80}?already\s+on\s+main') -or
        ($joined -match '(?i)already\s+on\s+main[\s\S]{0,80}?Thin\s+FAIL[- ]supersede') -or
        # FR #4308: a-search#1980/#2283 - "thinner ... tip" + durable lesson already on main
        # (not contiguous "thin harvest tip"; no tip-loop meta / Thin FAIL order)
        ($joined -match '(?i)thinner?\b[\s\S]{0,120}?(?:harvest\s+)?tip') -or
        ($joined -match '(?i)FAIL[- ]supersede[d]?\b[\s\S]{0,220}?already\s+on\s+main') -or
        ($joined -match '(?i)durable\s+lesson\s+already') -or
        ($joined -match '(?i)closed\s+unmerged[\s\S]{0,100}?already\s+on\s+main') -or
        # FR #4484: "restates main" / "admit main already has" (a-search#3470)
        ($joined -match '(?i)restate(?:s|ing)?\s+main') -or
        ($joined -match '(?i)admit\s+main\s+already\s+has')
    )
    if ($isFailSuper -and $isProcess) { return $true }
    if ($isProcess -and ($joined -match '(?i)park(?:ed|s)?\s+under\s+harvest')) { return $true }
    if ($isFailSuper -and $isThinTwin) { return $true }  # FR #2991 / #3827 / #3959 / #4231 / #4308 / #4484
    # FR #4176: CLOSED wrong-book / light-triage DONE PASS (FR #3317) process-loop
    # closeouts re-open lesson(harvest) tips without the FAIL-supersede token (class of #4175).
    $isClosedWrongBook = ($joined -match '(?i)CLOSED\s+wrong[- ]book')
    $isLightTriagePass = ($joined -match '(?i)DONE\s+PASS[^\n]{0,100}(?:FR\s*#?\s*)?3317|(?:FR\s*#?\s*)?3317[^\n]{0,100}DONE\s+PASS')
    $isProcessLoopCue = ($joined -match '(?i)process[- ]loops?')
    if ($isClosedWrongBook -and $isProcess) { return $true }
    if ($isClosedWrongBook -and $isLightTriagePass) { return $true }
    if ($isProcessLoopCue -and ($isProcess -or $isClosedWrongBook -or $isFailSuper)) { return $true }
    # Broaden park: under harvest/SKILL.md without the word park (tip #4171/#4175 class)
    if ($isProcess -and ($joined -match '(?i)under\s+(?:`?harvest|harvest/SKILL)')) { return $true }
    return $false
}
if (Test-HarvestFailSupersedeProcessLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest FAIL-supersede process loop (FR #2970/#2991/#3827/#4176/#4207/#4231/#4308/#4484): not filing lesson(harvest) for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}


# FR #4357: PASS of a harvest-lesson / docs/mrb tip already lands (or arms) the durable
# lesson. Harvesting the MRB *process* playbook (merge origin/main, re-arm, DONE PASS)
# opens another harvest-lesson tip and floods the a-search MRB queue. Skip client-side.
# Distinct from FR #2970/#4231 (FAIL-supersede) and FR #4288 (ExistingPrUrl).
function Test-HarvestLessonMrbPassLoop([string]$SummaryText, [string[]]$LessonLines) {
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    $isLessonTip = (
        ($joined -match '(?i)harvest[- ]lesson') -or
        ($joined -match '(?i)docs/mrb') -or
        ($joined -match '(?i)lesson\(harvest')
    )
    $isPass = (
        ($joined -match '(?i)\bDONE\s+PASS\b') -or
        ($joined -match '(?i)MRB\s+re-offer') -or
        ($joined -match '(?i)\bre-offer\b.*\bPASS\b') -or
        ($joined -match '(?i)\bPASS\b.*\bre-offer\b') -or
        ($joined -match '(?i)light\s+triage[^\n]{0,80}\bPASS\b')
    )
    $isProcess = (
        ($joined -match '(?i)merge\s+origin/main') -or
        ($joined -match '(?i)re-arm') -or
        ($joined -match '(?i)--auto\s+--squash') -or
        ($joined -match '(?i)fr106/?108[^\n]{0,40}--ours') -or
        ($joined -match '(?i)checkout\s+--ours') -or
        ($joined -match '(?i)keep-both')
    )
    if ($isLessonTip -and $isPass -and $isProcess) { return $true }
    return $false
}
if (Test-HarvestLessonMrbPassLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest lesson-MRB PASS loop (FR #4357): not filing another harvest-lesson tip for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

# FR #5483 / FR #4288: ExistingPrUrl skip runs before lesson-review so stdout stays
# SKIPPED harvest ExistingPrUrl tip-loop (FR #4288) when a covering PR is linked.
# Durable work lives on that PR (FR #1812). Product -Repo harvest-agent-skills
# without ExistingPrUrl stays (FR #3189); do not redirect those lessons to bobiverse.
function Test-HarvestExistingPrUrlSkip([string]$ExistingUrl, [string]$SummaryText, [string[]]$LessonLines) {
    $eu = ([string]$ExistingUrl).Trim()
    if ($eu -and ($eu -match '(?i)https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+')) {
        return $true
    }
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    if ($joined -match '(?i)https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+') {
        return $true
    }
    return $false
}
if (Test-HarvestExistingPrUrlSkip -ExistingUrl $ExistingPrUrl -SummaryText $Summary -LessonLines $Lesson) {
    $cite = ([string]$ExistingPrUrl).Trim()
    if (-not $cite) {
        $m = [regex]::Match((@($Summary) + @($Lesson)) -join "`n", '(?i)https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+')
        if ($m.Success) { $cite = $m.Value }
    }
    Write-Host ("SKIPPED harvest ExistingPrUrl tip-loop (FR #4288 / #1812): linked {0}; not filing a second lesson tip for: {1}" -f $cite, $Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))
    return
}

# FR #4780: MRB/review of a harvest-lesson (or skills-only) PR must not open a new
# harvest-lesson tip. Honesty-box for reviewing lessons is the review itself.
# FR #4917: also FIX / re-DONE on lesson or docs/mrb pin jobs (mrbNNNN pin names;
# CLOSED harvest tip); do not require \bMRB\b alone.
# Also skip lessons whose subject is reviewing / harvesting / closing lessons, and
# dedup against open+closed harvest-lesson PRs from the last 24h (any seat).
function Test-HarvestLessonReviewLoop([string]$SummaryText, [string[]]$LessonLines) {
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    $isLessonContext = (
        ($joined -match '(?i)harvest[- ]lesson') -or
        ($joined -match '(?i)lesson\(harvest') -or
        ($joined -match '(?i)docs/mrb') -or
        ($joined -match '(?i)\bmrb\d{3,}\b') -or
        ($joined -match '(?i)skills[- ]only') -or
        ($joined -match '(?i)Harvested[- ]lessons') -or
        ($joined -match '(?i)light\s+triage')
    )
    # FR #4917: job closeout for MRB *or* FIX (and bare DONE PASS/FAIL) on lesson/pin tips.
    $isJobCloseout = (
        ($joined -match '(?i)\bMRB\b') -or
        ($joined -match '(?i)\bFIX\b') -or
        ($joined -match '(?i)\bDONE\s+(?:PASS|FAIL)\b') -or
        ($joined -match '(?i)\bDONE\s+FIX\b') -or
        ($joined -match '(?i)CLOSED\s+not[- ]useful') -or
        ($joined -match '(?i)CLOSED\s+already[- ]covered') -or
        ($joined -match '(?i)CLOSED\s+wrong[- ]path') -or
        ($joined -match '(?i)CLOSED\s+harvest\s+tip') -or
        ($joined -match '(?i)CLOSED[- ]duplicate') -or
        ($joined -match '(?i)FAIL[- ]supersede') -or
        ($joined -match '(?i)\breview(?:ing|ed|s)?\b')
    )
    $isMetaSubject = (
        ($joined -match '(?i)review(?:ing|ed|s)?\s+(?:harvest[- ]?lesson|lesson\s+tips?|lessons?\b)') -or
        ($joined -match '(?i)(?:harvest(?:ing)?|clos(?:e|ing)|FAIL[- ]supersede)\s+(?:harvest[- ]?lesson|lesson\s+tips?|lessons?\b)') -or
        ($joined -match '(?i)(?:about|when)\s+(?:reviewing|harvesting|closing)\s+lessons?') -or
        ($joined -match '(?i)do not (?:harvest|open|land|merge)\s+a\s+(?:new|second)\s+(?:harvest[- ]?lesson|lesson)\s+(?:tip|PR|bullet)') -or
        ($joined -match '(?i)second\s+Harvested[- ]lessons\s+bullet') -or
        ($joined -match '(?i)tip[- ]?loop') -or
        ($joined -match '(?i)process\s+meta') -or
        ($joined -match '(?i)lesson[- ]review') -or
        ($joined -match '(?i)do not invent a second tip')
    )
    if ($isMetaSubject) { return $true }
    if ($isLessonContext -and $isJobCloseout) { return $true }
    return $false
}
if (Test-HarvestLessonReviewLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest lesson-review loop (FR #4780/#4917): not filing lesson tip after reviewing/closing lessons for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

# FR #4917: when Summary/Lesson/-ExistingPrUrl cites a PR, ask GitHub whether that PR is
# a harvest-lesson or docs/mrb pin. Skip tip filing for every job kind (metadata, not regex).
function Test-IsLessonOrPinPrMeta {
    param(
        [string]$Title = '',
        [string[]]$Labels = @(),
        [string]$HeadRef = ''
    )
    $labs = @($Labels | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($labs -contains 'harvest-lesson') { return $true }
    if ($Title -match '(?i)^lesson\s*\(') { return $true }
    if ($Title -match '(?i)^docs/mrb-') { return $true }
    if ($HeadRef -match '(?i)^docs/mrb-') { return $true }
    if ($HeadRef -match '(?i)^intake/') { return $true }
    return $false
}
function Test-HarvestLessonOrPinJobSkip {
    param(
        [string]$RepoName,
        [string]$ExistingUrl,
        [string]$SummaryText,
        [string[]]$LessonLines
    )
    # FR #5109: pytest / seats without a stable gh view must not depend on live GitHub.
    if ($NoCitedPrLookup -or $env:BOBIVERSE_HARVEST_NO_GH_PR_LOOKUP -eq '1') {
        return $false
    }
    $joined = (@([string]$SummaryText) + @($LessonLines) + @([string]$ExistingUrl)) -join "`n"
    $refs = New-Object System.Collections.Generic.List[object]
    foreach ($m in [regex]::Matches($joined, '(?i)https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(\d+)')) {
        $refs.Add([pscustomobject]@{ Repo = $m.Groups[1].Value; Number = [int]$m.Groups[2].Value })
    }
    foreach ($m in [regex]::Matches($joined, '(?i)\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b')) {
        $refs.Add([pscustomobject]@{ Repo = $m.Groups[1].Value; Number = [int]$m.Groups[2].Value })
    }
    if ($RepoName -and ($joined -match '(?i)(?:^|[\s:/])#(\d+)\b')) {
        foreach ($m in [regex]::Matches($joined, '(?i)(?:FIX|MRB|PR|pull)\s+[^\n]{0,40}#(\d+)')) {
            $refs.Add([pscustomobject]@{ Repo = $RepoName; Number = [int]$m.Groups[1].Value })
        }
    }
    if (-not $refs.Count) { return $false }
    $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCmd) { return $false }
    $seen = @{}
    foreach ($ref in $refs) {
        $key = ("{0}#{1}" -f $ref.Repo, $ref.Number).ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        try {
            $raw = & gh pr view $ref.Number --repo $ref.Repo --json title,labels,headRefName 2>$null
            if (-not $raw) { continue }
            $pr = $raw | ConvertFrom-Json
            $labs = @()
            if ($pr.labels) {
                $labs = @($pr.labels | ForEach-Object {
                        if ($_.PSObject.Properties['name']) { [string]$_.name } else { [string]$_ }
                    })
            }
            if (Test-IsLessonOrPinPrMeta -Title ([string]$pr.title) -Labels $labs -HeadRef ([string]$pr.headRefName)) {
                return $true
            }
        } catch {
            # offline / rate-limit: fall through; text skip above still applies
        }
    }
    return $false
}
if (Test-HarvestLessonOrPinJobSkip -RepoName $Repo -ExistingUrl $ExistingPrUrl -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest lesson/pin job (FR #4917): cited PR is harvest-lesson or docs/mrb pin; not filing tip for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

# FR #4371: CLOSED-duplicate / CAST IRON already-covers harvest-lesson MRBs that only
# restate job-mrb "Re-offered or already-merged MRB" must not open lesson(harvest) tips
# (class of #4366/#4368/#4370 tip-loop; tip bodies also auto-linked Closes #productFR).
function Test-HarvestClosedDuplicateLessonLoop([string]$SummaryText, [string[]]$LessonLines) {
    $joined = (@([string]$SummaryText) + @($LessonLines)) -join "`n"
    $isHarvestLesson = (
        ($joined -match '(?i)harvest[- ]lesson') -or
        ($joined -match '(?i)lesson\(harvest') -or
        ($joined -match '(?i)Harvest-lesson\s+MRB')
    )
    $isClosedDup = (
        ($joined -match '(?i)CLOSED\s+duplicate') -or
        ($joined -match '(?i)CLOSED[- ]duplicate') -or
        ($joined -match '(?i)CLOSE(?:D)?\s+as\s+duplicate') -or
        ($joined -match '(?i)CAST\s+IRON\s+already\s+covers') -or
        ($joined -match '(?i)already\s+covers?\b[\s\S]{0,80}?CAST\s+IRON')
    )
    $isAlreadyMergedPlaybook = (
        ($joined -match '(?i)already[- ]merged\s+(?:bobiverse\s+)?MRB') -or
        ($joined -match '(?i)Re-offered\s+or\s+already[- ]merged\s+MRB') -or
        ($joined -match '(?i)already[- ]merged/re-offer') -or
        ($joined -match '(?i)job-mrb\s+(?:Harvest\s+)?digest') -or
        ($joined -match '(?i)already\s+in\s+(?:bobiverse-)?job-mrb') -or
        ($joined -match '(?i)weaker\s+harvest/SKILL') -or
        ($joined -match '(?i)never\s+Closes\s+a\s+product\s+FR')
    )
    if ($isHarvestLesson -and $isClosedDup -and $isAlreadyMergedPlaybook) { return $true }
    if ($isHarvestLesson -and $isClosedDup -and ($joined -match '(?i)job-mrb')) { return $true }
    # CAST IRON already covers + CLOSED + job-mrb/already-merged (tip #4370 class without harvest-lesson token)
    if (($joined -match '(?i)CAST\s+IRON\s+already\s+covers') -and ($joined -match '(?i)\bCLOSED\b') -and $isAlreadyMergedPlaybook) {
        return $true
    }
    return $false
}
if (Test-HarvestClosedDuplicateLessonLoop -SummaryText $Summary -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest CLOSED-duplicate lesson loop (FR #4371): not filing lesson(harvest) for: $($Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length)))"
    return
}

# FR #3824: if an open harvest-lesson PR already carries the same lesson text,
# skip filing (intake also links open twins; this avoids a second POST).
# FR #4953: any seat; also match title stem / distinctive tokens (a-search #4866-#4877).
# FR #4780: also dedup against open AND closed harvest-lesson PRs from the last 24h
# (any seat) so MRB reviews of lessons cannot re-file the same playbook tip.
function Get-HarvestLessonTitleStem([string]$Title) {
    $t = (([string]$Title).ToLowerInvariant() -replace '\s+', ' ').Trim()
    $t = [regex]::Replace($t, '^lesson\([^)]+\):\s*', '')
    $t = [regex]::Replace($t, '\.{2,}$', '').Trim()
    if ($t.Length -gt 56) { $t = $t.Substring(0, 56) }
    return $t
}

function Test-HarvestLessonTitleStemsMatch([string]$A, [string]$B) {
    $sa = Get-HarvestLessonTitleStem $A
    $sb = Get-HarvestLessonTitleStem $B
    if ($sa.Length -lt 28 -or $sb.Length -lt 28) { return $false }
    if ($sa.Contains($sb) -or $sb.Contains($sa)) { return $true }
    $n = [Math]::Min([Math]::Min($sa.Length, $sb.Length), 48)
    return ($n -ge 32 -and $sa.Substring(0, $n) -eq $sb.Substring(0, $n))
}

function Test-HarvestLessonDistinctiveOverlap([string]$ExistingBlob, [string]$NewLesson) {
    $generic = [System.Collections.Generic.HashSet[string]]::new([string[]]@(
        'selftest','entry','require','must','gate','fixture','probes','probe','local',
        'provider','providers','checks','behind','unless','absent','skip','green','stay',
        'without','deps','typeof','function','config','box','the','and','for','with',
        'that','this','from','when','into','secrets','harvest','agent','skills','skill',
        'invoke','intake','machine','source','book','seat','lesson','lessons','session',
        'summary','search','html','utf8','flamingo','ionos','marchhare'
    ))
    $tok = {
        param($text)
        $out = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($m in [regex]::Matches((([string]$text).ToLowerInvariant()), '[a-z0-9_]{4,}')) {
            $w = $m.Value.Trim('_')
            if ($w.EndsWith('able') -and $w.Length -gt 8) { $w = $w.Substring(0, $w.Length - 4) }
            elseif ($w.EndsWith('ed') -and $w.Length -gt 6) { $w = $w.Substring(0, $w.Length - 2) }
            if ($w.Length -ge 4 -and -not $generic.Contains($w)) { [void]$out.Add($w) }
        }
        return $out
    }
    $a = & $tok $ExistingBlob
    $b = & $tok $NewLesson
    $shared = 0
    foreach ($w in $a) {
        if ($b.Contains($w)) { $shared++ }
    }
    return ($shared -ge 2)
}

function Test-HarvestPrCoversLesson {
    param(
        [string]$PrTitle,
        [string]$PrBody,
        [string[]]$LessonLines
    )
    $blob = ((([string]$PrTitle) + "`n" + ([string]$PrBody)).ToLowerInvariant() -replace '\s+', ' ')
    foreach ($L in @($LessonLines)) {
        $key = (($L.ToLowerInvariant()) -replace '\s+', ' ').Trim()
        if (-not $key -or $key -eq '(no new playbook line)') { continue }
        if ($blob.Contains($key)) { return $true }
        $short = $key.Substring(0, [Math]::Min(80, $key.Length))
        if ($short.Length -ge 40 -and $blob.Contains($short)) { return $true }
        if (Test-HarvestLessonTitleStemsMatch -A $PrTitle -B $L) { return $true }
        if (Test-HarvestLessonTitleStemsMatch -A $PrTitle -B $key) { return $true }
        if (Test-HarvestLessonDistinctiveOverlap -ExistingBlob $blob -NewLesson $key) { return $true }
    }
    return $false
}

function Test-HarvestOpenLessonTwin {
    param(
        [string]$RepoName,
        [string[]]$LessonLines,
        [string]$Seat
    )
    if (-not $RepoName) { return $false }
    $lessons = @(
        $LessonLines |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ -and $_ -ne '(no new playbook line)' }
    )
    if (-not $lessons.Count) { return $false }
    $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCmd) { return $false }
    try {
        $raw = & gh pr list --repo $RepoName --state open --label harvest-lesson --limit 40 --json title,body,url 2>$null
        if ($raw) {
            $prs = $raw | ConvertFrom-Json
            foreach ($pr in @($prs)) {
                # FR #4953: any seat (seat arg kept for callers / logs).
                if (Test-HarvestPrCoversLesson -PrTitle ([string]$pr.title) -PrBody ([string]$pr.body) -LessonLines $lessons) {
                    return $true
                }
            }
        }
    } catch {
        # fall through
    }
    return $false
}

function Test-HarvestRecentLessonDedup {
    param(
        [string]$RepoName,
        [string[]]$LessonLines
    )
    if (-not $RepoName) { return $false }
    $lessons = @(
        $LessonLines |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ -and $_ -ne '(no new playbook line)' }
    )
    if (-not $lessons.Count) { return $false }
    $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCmd) { return $false }
    try {
        $raw = & gh pr list --repo $RepoName --state all --label harvest-lesson --limit 50 --json title,body,url,createdAt,closedAt 2>$null
        if (-not $raw) { return $false }
        $prs = $raw | ConvertFrom-Json
        if (-not $prs) { return $false }
        $cutoff = (Get-Date).ToUniversalTime().AddHours(-24)
        foreach ($pr in @($prs)) {
            $created = $null
            try { $created = [datetime]::Parse([string]$pr.createdAt).ToUniversalTime() } catch { continue }
            if ($created -lt $cutoff) { continue }
            if (Test-HarvestPrCoversLesson -PrTitle ([string]$pr.title) -PrBody ([string]$pr.body) -LessonLines $lessons) {
                return $true
            }
        }
    } catch {
        return $false
    }
    return $false
}

# FR #4371 / #4099 / #4419: GitHub auto-links Closes #N / Fixes #N in PR bodies. Harvest tip
# narratives that mention "Closes #4363" close product FRs. Replace the keyword with
# "closing-keyword" so the issue number remains but GitHub does not auto-close.
function Protect-HarvestBodyClosesKeywords([string]$Text) {
    # FR #4371 / #4099 / #4419: GitHub auto-links Closes #N / Fixes #N (and Closes #N/#M)
    # in PR bodies. Harvest tip narratives that mention product closes poison
    # closingIssuesReferences. Replace the keyword with "closing-keyword".
    if (-not $Text) { return $Text }
    $t = [string]$Text
    $t = [regex]::Replace($t, '(?i)\b(?:Closes|Fixes)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+)', 'closing-keyword $1')
    $t = [regex]::Replace($t, '(?i)\b(?:Closes|Fixes)\s+(#\d+(?:/#\d+)+)', 'closing-keyword $1')
    $t = [regex]::Replace($t, '(?i)\b(?:Closes|Fixes)\s+(#\d+)', 'closing-keyword $1')
    return $t
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
$body = Protect-HarvestBodyClosesKeywords $body
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
# FR #4514: a lesson that names a skill book ("belongs in bobiverse-bob-job-irc")
# wins over FR #3004 keyword inference (done-miss must not retarget that lesson).
$namedBook = $null
foreach ($candidate in @(
        'bobiverse-bob-job-irc', 'bobiverse-bob-job-mrb', 'bobiverse-bob-job-fr',
        'bobiverse-bob-job-uat', 'bobiverse-bob-worker', 'bobiverse-bob-commands',
        'bobiverse-bob-troubleshooting', 'bobiverse-bob-plan', 'bobiverse-worker-seat',
        'bobiverse-fleet-ops', 'bobiverse-bob', 'bobiverse-jeeves-commands',
        'bobiverse-jeeves-monitor', 'bobiverse-jeeves-troubleshooting', 'bobiverse-jeeves',
        'bobiverse-airc-commands', 'bobiverse-airc-troubleshooting', 'bobiverse-airc',
        'harvest-agent-skills', 'harvest-skills-visionary', 'harvest'
    )) {
    $escaped = [regex]::Escape($candidate)
    if ($inferBlob -match "(?:belongs in|belong in|durable home is|file in)\s+``?$escaped``?") {
        $namedBook = $candidate
        break
    }
}
if ($namedBook) {
    $bookName = $namedBook
    Write-Host "INFO FR #4514 explicit skill_book=$namedBook (keyword inference does not override)"
}
# FR #3004: default harvest yields to an inferred product book from Summary+Lesson cues
# (mirrors intake resolve_skill_book soft override) so bob-worker playbooks are not
# re-opened as lesson(harvest) when the owning skill already has the bullet.
if (-not $namedBook -and $bookName -eq 'harvest') {
    # Strong product cues only - bare "MRB"/"UAT" in session summaries must not re-route.
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
# FR #3959: always route Bob tooling to bobiverse even when seats pass explicit
# -Repo <product> (FR #3189 job-repo). Otherwise FR #3004 sets bobiverse-bob-worker
# and opens ADD stubs under bob/ inside a-search (#3952/#3956).
if ($bobTooling) {
    if ($Repo -notmatch '(?i)^SimonBarnett/bobiverse$') {
        Write-Host "INFO FR #3189/#3959 split: Bob tooling lesson -> repo=SimonBarnett/bobiverse (was $Repo)"
    }
    $Repo = 'SimonBarnett/bobiverse'
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/a-search$')) {
    $bookName = 'harvest-agent-skills'
    Write-Host "INFO FR #3189 product default skill_book=harvest-agent-skills for SimonBarnett/a-search"
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/skills-visionary$')) {
    $bookName = 'harvest-skills-visionary'
    Write-Host "INFO FR #3317 product default skill_book=harvest-skills-visionary for SimonBarnett/skills-visionary"
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/agentic_fomprep$')) {
    $bookName = 'harvest-agent-skills'
    Write-Host "INFO FR #3318 product default skill_book=harvest-agent-skills for SimonBarnett/agentic_fomprep"
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/(euroflo|lynton|trutex|rees)$')) {
    # FR #4990 / euroflo#15: priority-customer topic peers share repo-root honesty box.
    $bookName = 'harvest-agent-skills'
    Write-Host "INFO FR #4990 priority-customer default skill_book=harvest-agent-skills for $Repo"
} elseif ($bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/ce-priority$')) {
    # FR #4830: even with explicit -Book harvest, never invent common/.grok/skills/harvest
    # on ce-priority (assert-lock / tip-loop class of ce-priority#36/#37/#38).
    $bookName = 'dayworks-launcher'
    Write-Host "INFO FR #4830 product default skill_book=dayworks-launcher for SimonBarnett/ce-priority (never invent common/.grok/skills/harvest)"
} elseif (-not $script:ExplicitBook -and $bookName -eq 'harvest' -and ($Repo -match '(?i)^SimonBarnett/' ) -and ($Repo -notmatch '(?i)^SimonBarnett/bobiverse$')) {
    # FR #4976: other SimonBarnett product/customer repos (topic set may be empty).
    $bookName = 'harvest-agent-skills'
    Write-Host "INFO FR #4976 product default skill_book=harvest-agent-skills for $Repo (not common/.grok/skills/harvest)"
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
    '^dayworks-launcher$' { $skillBookPath = 'dayworks/.grok/skills/dayworks-launcher/SKILL.md' }
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

# FR #3824: client-side skip when an open tip from this seat already has the lesson.
if (Test-HarvestOpenLessonTwin -RepoName $Repo -LessonLines $Lesson -Seat $seatNick) {
    Write-Host "SKIPPED harvest open lesson twin (FR #3824/#4953): open harvest-lesson PR already covers this lesson (any seat; cite existing PR; lesson_already_covered)"
    return
}
if (Test-HarvestRecentLessonDedup -RepoName $Repo -LessonLines $Lesson) {
    Write-Host "SKIPPED harvest recent lesson dedup (FR #4780): open/closed harvest-lesson PR in last 24h already carries this lesson"
    return
}

# FR #3824: prefer seat+normalized-lesson idempotency material so Summary drift /
# DONE retries do not mint a second intake id for the same tip.
$lessonKeyParts = @(
    $Lesson |
        ForEach-Object {
            $t = ([string]$_).Trim().ToLowerInvariant()
            $t = ($t -replace '\s+', ' ')
            if ($t -and $t -ne '(no new playbook line)') { $t }
        }
)
$lessonKey = ($lessonKeyParts -join '|')
if ($lessonKey) {
    $idemMaterial = "$Repo|$bookName|$seatNick|$lessonKey"
} else {
    $idemMaterial = "$Repo|$title|$body"
}
$sha = [Security.Cryptography.SHA256]::Create()
$idem = 'hv-' + ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($idemMaterial))) -replace '-', '').Substring(0, 24).ToLowerInvariant()
$payload = [ordered]@{
    kind = 'harvest'; repo = $Repo; title = $title; body = $body; idempotency_key = $idem
    skill_book_path = $skillBookPath
    source = [ordered]@{ machine = $Machine.Substring(0, [Math]::Min(64, $Machine.Length)); agent = 'Invoke-BobiverseHarvest'; skill_book = $bookName; skill_book_path = $skillBookPath; version = $script:HarvestScriptVersion; seat = $seatNick }
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
