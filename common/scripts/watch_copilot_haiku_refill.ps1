# FR #9846: tip-allowlist bypass for SKIP_FAILED_LOOP; infra missing_conclusion
# does not burn the fail-loop budget (ties #9782). Pure helpers live in
# common/scripts/copilot_haiku_refill.py (tests: test_fr9846_tip_allowlist_fail_loop.py).
param(
  [int]$TargetHaiku = 2,
  [string]$Model = 'claude-haiku-4.5',
  [string]$Repo = 'SimonBarnett/bobiverse'
)
$ErrorActionPreference = 'Continue'
$utf8 = New-Object System.Text.UTF8Encoding $false
# Tip path allowlist (operational). Override with BOB_COPILOT_TIP_ALLOWLIST=1,2,3
$script:JeevesBuildAllow = @(9840, 9821, 9826, 9827, 9782, 9781)
if ($env:BOB_COPILOT_TIP_ALLOWLIST) {
  $script:JeevesBuildAllow = @(
    $env:BOB_COPILOT_TIP_ALLOWLIST.Split(',') |
      ForEach-Object { $_.Trim() } |
      Where-Object { $_ -match '^\d+$' } |
      ForEach-Object { [int]$_ }
  )
}
# Map FR -> covering tip PR (skip FR when that PR build-jeeves is already green).
$script:TipPrByFr = @{ 9840 = 9842; 9821 = 9834; 9826 = 9829; 9827 = 9839; 9782 = 9789; 9781 = 9788 }
$script:HaikuRefillPy = Join-Path $PSScriptRoot 'copilot_haiku_refill.py'
$lockPath = Join-Path $env:TEMP 'watch_copilot_haiku_refill.lock'
try {
  $script:lock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
  Write-Output 'SKIP locked by another refill'
  exit 0
}

# Returns $null on API failure; otherwise PSCustomObject @{ Hits = [object[]] } (Hits may be empty).
function Get-HaikuInProgress {
  $raw = (gh api "agents/repos/$Repo/tasks" 2>&1 | Out-String).Trim()
  if ($raw -match 'rate limit exceeded|API rate limit') { Write-Host 'RATE_LIMIT list'; return $null }
  if ($raw.Length -lt 2 -or $raw[0] -ne '{') { return $null }
  try { $list = $raw | ConvertFrom-Json } catch { return $null }
  $hits = New-Object System.Collections.ArrayList
  foreach ($t in @($list.tasks)) {
    if ($t.state -notin @('in_progress','queued')) { continue }
    $detRaw = (gh api ($t.url -replace 'https://api.github.com/','') 2>&1 | Out-String).Trim()
    if ($detRaw -match 'rate limit') { break }
    if ($detRaw.Length -lt 2 -or $detRaw[0] -ne '{') { continue }
    try { $det = $detRaw | ConvertFrom-Json } catch { continue }
    $m = ''; $prompt = ''
    try { $m = [string]$det.sessions[0].model } catch {}
    try { $prompt = [string]$det.sessions[0].prompt } catch {}
    if ($m -notmatch 'haiku' -and $prompt -notmatch 'virtual seat nick=copilot') { continue }
    $issue = $null
    if ($prompt -match 'FR\s*#(\d+)') { $issue = [int]$Matches[1] }
    [void]$hits.Add([pscustomobject]@{ id = $t.id; state = $t.state; model = $m; issue = $issue })
  }
  return [pscustomobject]@{ Hits = @($hits.ToArray()) }
}

function Get-FailedLoopIds {
  $failed = @{}
  $raw = (gh api "agents/repos/$Repo/tasks?per_page=30" 2>&1 | Out-String).Trim()
  if ($raw -match 'rate limit') { Write-Host 'RATE_LIMIT failed-scan'; return [int[]]@() }
  if ($raw.Length -lt 2 -or $raw[0] -ne '{') { return [int[]]@() }
  try { $list = $raw | ConvertFrom-Json } catch { return [int[]]@() }
  $cutoff = [datetime]::UtcNow.AddHours(-3)
  foreach ($t in @($list.tasks)) {
    if ($t.state -ne 'failed') { continue }
    try {
      $created = [datetime]::Parse([string]$t.created_at, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
      if ($created -lt $cutoff) { continue }
    } catch { continue }
    $detRaw = (gh api ($t.url -replace 'https://api.github.com/','') 2>&1 | Out-String).Trim()
    if ($detRaw -match 'rate limit' -or $detRaw.Length -lt 2 -or $detRaw[0] -ne '{') { continue }
    try { $det = $detRaw | ConvertFrom-Json } catch { continue }
    # FR #9846 / #9782: infra soft-fail must not burn fail-loop budget.
    if ($detRaw -match 'missing_conclusion|conclusion is not available|conclusion_not_available') {
      Write-Host 'SKIP_INFRA_SOFT_FAIL (missing_conclusion)'
      continue
    }
    $prompt = ''
    try { $prompt = [string]$det.sessions[0].prompt } catch {}
    if ($prompt -match 'FR\s*#(\d+)') {
      $n = [int]$Matches[1]
      if (-not $failed.ContainsKey($n)) { $failed[$n] = 0 }
      $failed[$n]++
    }
  }
  $skip = @($failed.GetEnumerator() | Where-Object { $_.Value -ge 2 } | ForEach-Object { [int]$_.Key })
  if ($skip.Count -gt 0) { Write-Host ("SKIP_FAILED_LOOP issues={0}" -f ($skip -join ',')) }
  return [int[]]@($skip)
}

function Invoke-TipAllowlistFailLoopBypass {
  param(
    [int[]]$FailedSkip,
    [int[]]$Allowlist,
    [int[]]$OpenEligible
  )
  # Prefer Python helper (single source of truth with unit tests). Fall back to
  # inline logic if python/module unavailable.
  if (Test-Path -LiteralPath $script:HaikuRefillPy) {
    $tmpIn = $null
    $tmpPy = $null
    try {
      $payloadObj = @{
        failed_skip = @($FailedSkip)
        tip_allowlist = @($Allowlist)
        open_eligible = @($OpenEligible)
      }
      $tmpIn = Join-Path $env:TEMP ("haiku-refill-bypass-{0}.json" -f [guid]::NewGuid().ToString('N'))
      $tmpPy = Join-Path $env:TEMP ("haiku-refill-bypass-{0}.py" -f [guid]::NewGuid().ToString('N'))
      [IO.File]::WriteAllText($tmpIn, ($payloadObj | ConvertTo-Json -Compress), $utf8)
      $pyBody = @(
        'import json, sys'
        'from copilot_haiku_refill import apply_tip_allowlist_fail_loop_bypass'
        'doc = json.load(open(sys.argv[1], encoding="utf-8"))'
        'cleared, reason = apply_tip_allowlist_fail_loop_bypass('
        '    doc.get("failed_skip") or [],'
        '    doc.get("tip_allowlist") or [],'
        '    doc.get("open_eligible") or [],'
        ')'
        'json.dump({"failed_skip": sorted(int(x) for x in cleared), "reason": reason}, sys.stdout)'
      ) -join "`n"
      [IO.File]::WriteAllText($tmpPy, $pyBody, $utf8)
      $env:PYTHONPATH = [string]$PSScriptRoot
      $out = & python $tmpPy $tmpIn 2>&1 | Out-String
      $out = $out.Trim()
      if ($out.StartsWith('{')) {
        $doc = $out | ConvertFrom-Json
        return [pscustomobject]@{
          FailedSkip = [int[]]@($doc.failed_skip)
          Reason = $(if ($null -eq $doc.reason) { $null } else { [string]$doc.reason })
        }
      }
      Write-Host ("WARN tip-bypass python: {0}" -f $out.Substring(0, [Math]::Min(200, $out.Length)))
    } catch {
      Write-Host ("WARN tip-bypass python failed: {0}" -f $_.Exception.Message)
    } finally {
      if ($tmpIn) { Remove-Item -LiteralPath $tmpIn -Force -ErrorAction SilentlyContinue }
      if ($tmpPy) { Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue }
    }
  }
  # Inline fallback (keep behaviour aligned with copilot_haiku_refill.py).
  $skip = New-Object 'System.Collections.Generic.HashSet[int]'
  foreach ($n in @($FailedSkip)) { [void]$skip.Add([int]$n) }
  $allow = @($Allowlist | ForEach-Object { [int]$_ })
  $openTips = @($OpenEligible | ForEach-Object { [int]$_ })
  if ($allow.Count -eq 0 -or $skip.Count -eq 0) {
    return [pscustomobject]@{ FailedSkip = [int[]]@($skip); Reason = $null }
  }
  if ($openTips.Count -eq 0) {
    $blocked = @($allow | Where-Object { $skip.Contains([int]$_) })
    $reason = $(if ($blocked.Count -gt 0) { 'tip_allowlist_exhausted' } else { $null })
    return [pscustomobject]@{ FailedSkip = [int[]]@($skip); Reason = $reason }
  }
  $stillFree = @($openTips | Where-Object { -not $skip.Contains([int]$_) })
  if ($stillFree.Count -gt 0) {
    return [pscustomobject]@{ FailedSkip = [int[]]@($skip); Reason = $null }
  }
  $cleared = New-Object 'System.Collections.Generic.HashSet[int]'
  $allowSet = New-Object 'System.Collections.Generic.HashSet[int]'
  foreach ($a in $allow) { [void]$allowSet.Add([int]$a) }
  foreach ($n in $skip) { if (-not $allowSet.Contains([int]$n)) { [void]$cleared.Add([int]$n) } }
  return [pscustomobject]@{ FailedSkip = [int[]]@($cleared); Reason = 'tip_allowlist_bypass' }
}

function Test-TipPrAlreadyGreen {
  param([int]$IssueNumber)
  if (-not $script:TipPrByFr.ContainsKey($IssueNumber)) { return $false }
  $pr = [int]$script:TipPrByFr[$IssueNumber]
  $raw = gh pr view $pr -R $Repo --json state,statusCheckRollup 2>&1 | Out-String
  if ($raw -match 'rate limit') { Write-Host 'RATE_LIMIT pr-view'; return $true }
  try { $p = $raw | ConvertFrom-Json } catch { return $false }
  if ([string]$p.state -ne 'OPEN') { return $false }
  $bj = @($p.statusCheckRollup | Where-Object { $_.name -eq 'build-jeeves' } | Select-Object -First 1)
  if ($bj.Count -eq 0) { return $false }
  if ([string]$bj[0].conclusion -eq 'SUCCESS') {
    Write-Host ("SKIP_TIP_PR_GREEN FR#{0} PR#{1} build-jeeves=SUCCESS" -f $IssueNumber, $pr)
    return $true
  }
  return $false
}

function Test-DependsOnHeldDigest {
  param([int]$IssueNumber)
  # HARD GATE (Si 2026-11-24): never CCA kids of OPEN fr-digest+hold digests.
  if ($IssueNumber -ge 9800 -and $IssueNumber -le 9815) {
    Write-Host ("SKIP_HELD_RANGE FR#{0} (.NET bob-worker #9800-#9815)" -f $IssueNumber)
    return $true
  }
  $viewRaw = gh issue view $IssueNumber -R $Repo --json body,labels 2>&1 | Out-String
  if ($viewRaw -match 'rate limit') { Write-Host 'RATE_LIMIT issue-view'; return $true }
  try { $view = $viewRaw | ConvertFrom-Json } catch { return $false }
  $body = [string]$view.body
  $depNums = New-Object System.Collections.Generic.List[int]
  foreach ($m in [regex]::Matches($body, '(?im)Depends-on\s*:?\s*#(\d+)')) {
    $n = [int]$m.Groups[1].Value
    if (-not $depNums.Contains($n)) { [void]$depNums.Add($n) }
  }
  foreach ($dep in $depNums) {
    if ($dep -ge 9793 -and $dep -le 9799) {
      Write-Host ("SKIP_HELD_DIGEST FR#{0} Depends-on #{1} (phase digest range)" -f $IssueNumber, $dep)
      return $true
    }
    $depRaw = gh issue view $dep -R $Repo --json state,labels,number 2>&1 | Out-String
    if ($depRaw -match 'rate limit') { Write-Host 'RATE_LIMIT dep-view'; return $true }
    try { $depView = $depRaw | ConvertFrom-Json } catch { continue }
    if ([string]$depView.state -ne 'OPEN') { continue }
    $dl = @($depView.labels | ForEach-Object { $_.name })
    if (($dl -contains 'fr-digest') -and ($dl -contains 'hold')) {
      Write-Host ("SKIP_HELD_DIGEST FR#{0} Depends-on #{1} (fr-digest+hold OPEN)" -f $IssueNumber, $dep)
      return $true
    }
  }
  return $false
}

function Test-IsJeevesChairFr {
  param([string]$Title, [string]$Body)
  $blob = "$Title`n$Body"
  if ($blob -match '(?i)\.NET bob-worker|worker-net|bob-worker Phase') { return $false }
  if ($blob -match '(?i)chair:|offer_to_idle|sticky|recycle|stuck-sweep|ear single-instance|digest\.copilot|held fr-digest|offerable|!assign|!sweep|keep-queue') { return $true }
  if ($blob -match '(?i)ircJeeves|jeeves/|tools\\monitor|offer_after_done') { return $true }
  return $false
}

function Get-NextFr {
  param([Parameter(Mandatory = $false)][int[]]$SkipIssues = @())
  # Prefer allowlist order (9840 tip-red first) when locked to Jeeves build path.
  if ($script:JeevesBuildAllow) {
    foreach ($want in @($script:JeevesBuildAllow)) {
      if ($SkipIssues -contains [int]$want) { continue }
      if (Test-DependsOnHeldDigest -IssueNumber ([int]$want)) { continue }
      if (Test-TipPrAlreadyGreen -IssueNumber ([int]$want)) { continue }
      $viewRaw = gh issue view $want -R $Repo --json number,title,state,labels 2>&1 | Out-String
      if ($viewRaw -match 'rate limit') { Write-Host 'RATE_LIMIT issue-view'; return $null }
      try { $v = $viewRaw | ConvertFrom-Json } catch { continue }
      if ([string]$v.state -ne 'OPEN') { continue }
      $labs = @($v.labels | ForEach-Object { $_.name })
      if ($labs -contains 'fr-digest') { continue }
      if ($labs -contains 'needs-walrus') { continue }
      $t = [string]$v.title
      if ($t -match '^lesson\(') { continue }
      if ($t -match 'Weights Copilot|concurrent slot|digest\.copilot|Tray paints Copilot|Dispatch sends Weights|TipForm-restore') { continue }
      return [pscustomobject]@{ n = [int]$v.number; title = $t; url = ("https://github.com/{0}/issues/{1}" -f $Repo, $v.number) }
    }
    Write-Host 'NO_JEEVES_BUILD_FR'
    return $null
  }
  $raw = gh issue list -R $Repo --state open --label feature-request --limit 60 --json number,title,labels 2>&1 | Out-String
  if ($raw -match 'rate limit') { Write-Host 'RATE_LIMIT issues'; return $null }
  try { $rows = $raw | ConvertFrom-Json } catch { return $null }
  $heldOnly = $true
  $jeevesPick = $null
  $anyPick = $null
  foreach ($r in @($rows)) {
    $labs = @($r.labels | ForEach-Object { $_.name })
    if ($labs -contains 'fr-digest') { continue }
    if ($labs -contains 'needs-walrus') { continue }
    $t = [string]$r.title
    if ($t -match '^lesson\(') { continue }
    if ($t -match 'Weights Copilot|concurrent slot|digest\.copilot|Tray paints Copilot|Dispatch sends Weights|TipForm-restore') { continue }
    if ($SkipIssues -contains [int]$r.number) { continue }
    if (Test-DependsOnHeldDigest -IssueNumber ([int]$r.number)) { continue }
    $heldOnly = $false
    $body = ''
    try {
      $br = gh issue view ([int]$r.number) -R $Repo --json body 2>&1 | Out-String
      $body = [string](($br | ConvertFrom-Json).body)
    } catch {}
    $cand = [pscustomobject]@{ n = [int]$r.number; title = $t; url = ("https://github.com/{0}/issues/{1}" -f $Repo, $r.number) }
    if (-not $anyPick) { $anyPick = $cand }
    if ((Test-IsJeevesChairFr -Title $t -Body $body) -and (-not $jeevesPick)) { $jeevesPick = $cand }
  }
  if ($heldOnly -and -not $anyPick) {
    Write-Host 'NO_UNGATED_JEEVES_FR'
    return $null
  }
  if ($jeevesPick) { return $jeevesPick }
  if ($anyPick) {
    Write-Host ("WARN_NON_JEEVES_FALLBACK FR#{0}" -f $anyPick.n)
    return $anyPick
  }
  Write-Host 'NO_UNGATED_JEEVES_FR'
  return $null
}

function Start-HaikuFr($fr) {
  $prompt = "You are the bobiverse FR worker (virtual seat nick=copilot).`nRepo: $Repo  Job: FR #$($fr.n)  $($fr.url)`n$($fr.title)`nFollow AGENTS.md / CAST IRON. Never merge. Never print secrets.`nImplement. Open one PR with Closes $Repo#$($fr.n)."
  $body = @{ prompt = $prompt; base_ref = 'main'; model = $Model }
  $p = Join-Path $env:TEMP ("cca-refill-$($fr.n).json")
  [IO.File]::WriteAllText($p, ($body | ConvertTo-Json -Compress), $utf8)
  $out = gh api -X POST "agents/repos/$Repo/tasks" --input $p 2>&1 | Out-String
  if ($out -match 'rate limit') { Write-Host 'RATE_LIMIT post'; return $null }
  if ($out -notmatch '"id"') { Write-Host ("REFILL_FAIL FR#$($fr.n)"); return $null }
  try { $resp = $out | ConvertFrom-Json } catch { return $null }
  Write-Host ("REFILL_OK FR#$($fr.n) task=$($resp.id)")
  return $resp
}

try {
  $wrap = Get-HaikuInProgress
  if ($null -eq $wrap) { Write-Output 'ABORT list unavailable or rate-limited'; exit 2 }
  $haiku = @($wrap.Hits)
  Write-Output ("haiku_inflight={0} target={1}" -f $haiku.Count, $TargetHaiku)
  foreach ($h in $haiku) {
    Write-Output ("  {0} {1} FR#{2}" -f $h.state, $h.model, $h.issue)
    if ($script:JeevesBuildAllow -and $null -ne $h.issue -and ($script:JeevesBuildAllow -notcontains [int]$h.issue)) {
      Write-Output ("NOTE_OFF_ALLOWLIST FR#{0} (no cancel API)" -f $h.issue)
    }
  }
  if ($haiku.Count -ge $TargetHaiku) { Write-Output 'OK at target'; exit 0 }

  $fuelState = ''
  try {
    $rep = Invoke-RestMethod -Uri 'https://bob.ntsa.uk/bob/v1/report' -TimeoutSec 30
    if ($rep.copilot) { $fuelState = [string]$rep.copilot.state }
  } catch {}
  Write-Output ("copilot_state={0}" -f $(if ($fuelState) { $fuelState } else { 'unknown' }))
  # Soft pause on digest exhausted: still try refill unless POST fails (false exhaust #9781).

  $failedSkip = [int[]]@(Get-FailedLoopIds)
  # FR #9846: tip-allowlist bypass when fail-loop would zero every open tip FR.
  if ($script:JeevesBuildAllow -and $failedSkip.Count -gt 0) {
    $allowOpen = @()
    foreach ($want in @($script:JeevesBuildAllow)) {
      if (Test-TipPrAlreadyGreen -IssueNumber ([int]$want)) { continue }
      $viewRaw = gh issue view $want -R $Repo --json state,labels,title 2>&1 | Out-String
      try { $v = $viewRaw | ConvertFrom-Json } catch { continue }
      if ([string]$v.state -ne 'OPEN') { continue }
      $labs = @($v.labels | ForEach-Object { $_.name })
      if ($labs -contains 'fr-digest' -or $labs -contains 'needs-walrus') { continue }
      $t = [string]$v.title
      if ($t -match '^lesson\(' -or $t -match 'TipForm-restore') { continue }
      $allowOpen += [int]$want
    }
    $bypass = Invoke-TipAllowlistFailLoopBypass -FailedSkip $failedSkip -Allowlist $script:JeevesBuildAllow -OpenEligible $allowOpen
    if ($bypass.Reason -eq 'tip_allowlist_bypass') {
      Write-Output ("TIP_ALLOWLIST_BYPASS clearing failed-loop for tip FRs (open={0})" -f ($allowOpen -join ','))
      $failedSkip = [int[]]@($bypass.FailedSkip)
    } elseif ($bypass.Reason -eq 'tip_allowlist_exhausted') {
      Write-Output 'SKIP_FAILED_LOOP blocks all tip allowlist (no open/red tip FR left)'
    }
  }
  $knownIssues = New-Object System.Collections.Generic.List[int]
  foreach ($h in $haiku) {
    if ($null -ne $h.issue) { [void]$knownIssues.Add([int]$h.issue) }
  }
  foreach ($n in $failedSkip) { if (-not $knownIssues.Contains([int]$n)) { [void]$knownIssues.Add([int]$n) } }

  $inflight = $haiku.Count
  while ($inflight -lt $TargetHaiku) {
    $skip = [int[]]@($knownIssues.ToArray())
    $fr = Get-NextFr -SkipIssues $skip
    if (-not $fr) {
      if ($failedSkip.Count -gt 0 -and $script:JeevesBuildAllow) {
        Write-Output 'SKIP_FAILED_LOOP blocks all (or tip PRs already green)'
      }
      Write-Output 'NO_FR_CANDIDATE'
      break
    }
    $resp = Start-HaikuFr $fr
    if (-not $resp) { Write-Output 'POST failed/rate-limited — stop'; break }
    [void]$knownIssues.Add([int]$fr.n)
    $inflight++
    Start-Sleep -Seconds 5
  }
  Write-Output ("haiku_inflight_after={0}" -f $inflight)
} finally {
  if ($script:lock) { $script:lock.Close(); $script:lock.Dispose() }
}
