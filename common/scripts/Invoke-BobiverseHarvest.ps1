#Requires -Version 5.1
<#
.SYNOPSIS
  Harvest step for any Bobiverse debugging/maintenance session: file what you learned to the intake webhook.

.DESCRIPTION
  Builds ONE harvest payload (kind=harvest, repo SimonBarnett/bobiverse by default) from -Summary / -Lesson /
  optional -SkillFile contents and POSTs it to https://irc.ntsa.uk/bob/v1/intake. No password or token is needed.
  Offline or failing POSTs are written to harvest-outbox/ and resent by -Flush (same idempotency_key, so retries
  never duplicate). Refuses to send anything that looks like a secret. Prints a receipt (intake id) or the queue file.

  Use Report-BobiverseIntakeIssue.ps1 for individual bugs / FRs; use this script to close a session.

.EXAMPLE
  .\Invoke-BobiverseHarvest.ps1 -Summary 'ear restart loop' -Lesson 'Start-Bob must pass --host or the watcher kills the ear'
.EXAMPLE
  .\Invoke-BobiverseHarvest.ps1 -Flush
#>
[CmdletBinding()]
param(
    [string]$Summary = '',
    [string[]]$Lesson = @(),
    [string[]]$SkillFile = @(),
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$IntakeUrl = 'https://irc.ntsa.uk/bob/v1/intake',
    [string]$Machine = '',
    [string]$OutboxDir = '',
    [switch]$Flush,
    [switch]$DryRun,
    [int]$TimeoutSec = 30
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$secretRx = '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(password|passwd|secret|token|apikey|api_key)\s*[:=]\s*[A-Za-z0-9/+_.-]{8,}))'
$home1 = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
if (-not $OutboxDir) { $OutboxDir = Join-Path $home1 '.grok\bob\harvest-outbox' }
$headers = @{ 'Content-Type' = 'application/json' }
if ($env:BOB_INTAKE_KEY) { $headers['X-Bob-Intake-Key'] = [string]$env:BOB_INTAKE_KEY }

function Send-Payload([string]$Json) {
    return Invoke-RestMethod -Method Post -Uri $IntakeUrl -Headers $headers -Body $Json -TimeoutSec $TimeoutSec
}

if ($Flush) {
    $dirs = @($OutboxDir, (Join-Path (Get-Location).Path 'harvest-outbox'), (Join-Path (Get-Location).Path 'report-outbox'),
        (Join-Path $home1 '.grok\bob\report-outbox')) | Select-Object -Unique
    $sent = 0; $kept = 0
    foreach ($d in $dirs) {
        if (-not (Test-Path -LiteralPath $d)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $d -File -Filter '*.json' -ErrorAction SilentlyContinue)) {
            try {
                $r = Send-Payload (Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8)
                Remove-Item -LiteralPath $f.FullName -Force
                $sent++
                Write-Host "SENT $($f.Name) intake_id=$($r.intake_id)"
            } catch {
                $kept++
                Write-Host "KEPT $($f.FullName): $($_.Exception.Message)"
            }
        }
    }
    Write-Host "flush: sent=$sent kept=$kept"
    return
}

if (-not $Summary.Trim()) { throw '-Summary is required (what broke / what you fixed / "nothing new")' }
if (-not ($Repo -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')) { throw "Repo must be owner/name (got '$Repo')" }
if (-not $Machine) { $Machine = if ($env:BOB_MACHINE_ID) { [string]$env:BOB_MACHINE_ID } else { [string]$env:COMPUTERNAME } }

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

$title = 'harvest: ' + $Summary.Trim().Substring(0, [Math]::Min(80, $Summary.Trim().Length))
$sha = [Security.Cryptography.SHA256]::Create()
$idem = 'hv-' + ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes("$Repo|$title|$body"))) -replace '-', '').Substring(0, 24).ToLowerInvariant()
$payload = [ordered]@{
    kind = 'harvest'; repo = $Repo; title = $title; body = $body; idempotency_key = $idem
    source = [ordered]@{ machine = $Machine.Substring(0, [Math]::Min(64, $Machine.Length)); agent = 'Invoke-BobiverseHarvest'; skill_book = 'harvest'; version = '' }
}
if ($files.Count) { $payload.files = $files }
$json = $payload | ConvertTo-Json -Depth 6
if ($DryRun) { Write-Host $json; return }
try {
    $r = Send-Payload $json
    Write-Host "HARVESTED intake_id=$($r.intake_id) url=$($r.url) queued=$($r.queued)"
} catch {
    New-Item -ItemType Directory -Force -Path $OutboxDir | Out-Null
    $out = Join-Path $OutboxDir ("harvest-$idem.json")
    [IO.File]::WriteAllText($out, $json + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host "QUEUED $out ($($_.Exception.Message)); resend with: .\scripts\Invoke-BobiverseHarvest.ps1 -Flush"
}