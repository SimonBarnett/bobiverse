#Requires -Version 5.1
<#
.SYNOPSIS
  Fast-forward the install dir (a sparse git work tree of the bobiverse repo), then compose its flat runtime files.
.DESCRIPTION
  Used by Start-Jeeves / Start-Bob / Start-AircConsole before launch (t781u/t782u).
  1) Source: BOBIVERSE_REPO (explicit external clone), else the INSTALL DIR itself as a sparse work tree holding only
     <product>/ + common/ (bootstrapped on first run from BOBIVERSE_REMOTE, default the GitHub repo), else a shared clone
     <ai root>\bobiverse (ai root found on the fixed disks; BOB_AI_ROOT overrides)
  2) git fetch + merge --ff-only origin/main, only while on main (best-effort: never destroys local edits/commits/branches,
     never blocks service start, falls back to the installed files). FR #1157: if HEAD is on another branch but the tree is
     clean and either HEAD is already an ancestor of origin/main or that branch's upstream was deleted (gone), auto
     ``git switch main`` then ff - so a leftover fix/* after hotpatch cannot strand robocopy on a stale tip. Active agent
     work (dirty tree, never-pushed branch, or unique commits with a live upstream) is left alone. Opt out:
     BOBIVERSE_KEEP_BRANCH=1 (or BOBIVERSE_NO_UPDATE=1).
  3) Robocopy scripts + third_party + skills + docs into InstallRoot (never deleting); copy VERSION
  Skips when BOBIVERSE_NO_UPDATE=1. For -Product airc, also skips when config\airc.json
  sync_from_repo is false/absent (FR #3289; override BOBIVERSE_SYNC_FROM_REPO=1). Does not overwrite config\, home\, or secrets.
  FR #269: flat scripts/ is always refreshed from the split-repo script dirs (no robocopy /XO on scripts).
  Git checkout mtimes are often older than a previous flat compose, so /XO left scripts/gitclaim.py stale after ff.
  Use -ComposeOnly after a manual git pull --ff-only to recompose without restarting the service.
.PARAMETER ComposeOnly
  Skip fetch/ff; only recompose flat runtime files from the current work tree / clone (FR #269 operator hook).
.PARAMETER Product
  jeeves | bob | airc - selects default InstallRoot <ai root>\<product>.
.PARAMETER InstallRoot
  Product install tree to refresh (MSI layout without its own .git).
.PARAMETER Branch
  Remote branch to fast-forward (default main).
.OUTPUTS
  Exit 0 on success or soft-skip; exit 1 only when InstallRoot is missing/unusable.
#>
[CmdletBinding()]
param(
    [ValidateSet('jeeves', 'bob', 'airc')]
    [string]$Product = '',
    [string]$InstallRoot = '',
    [string]$Branch = 'main',
    [switch]$DryRun,
    [switch]$ComposeOnly,
    # Test hook (FR #1565): pretend ARP DisplayVersion is this value (skip registry).
    [string]$ArpVersionOverride = ''
)

$ErrorActionPreference = 'Stop'

if ($env:BOBIVERSE_NO_UPDATE -eq '1') {
    Write-Host 'INFO sync-skip BOBIVERSE_NO_UPDATE=1'
    exit 0
}

. (Join-Path $PSScriptRoot 'Bobiverse-Common.ps1')   # t780u: needed up front for the <drive>:\ai discovery
if (-not $InstallRoot) {
    if (-not $Product) { throw 'Sync-BobiverseFromRepo: pass -InstallRoot or -Product' }
    $InstallRoot = Get-BobiverseProductRoot -Product $Product   # t780u: discovered <drive>:\ai
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
if (-not (Test-Path -LiteralPath $InstallRoot)) {
    Write-Host "WARN sync-skip missing install root $InstallRoot"
    exit 1
}

# FR #3289 defense-in-depth (airc only): default sync_from_repo=off via config\airc.json.
# BOBIVERSE_SYNC_FROM_REPO=0|1 overrides. Missing key / missing file -> off when -Product airc.
if ($Product -eq 'airc') {
    $syncOn = $false
    $capPath = Join-Path $InstallRoot 'config\airc.json'
    if (Test-Path -LiteralPath $capPath) {
        try {
            $cap = Get-Content -LiteralPath $capPath -Raw -Encoding utf8 | ConvertFrom-Json
            if ($null -ne $cap.PSObject.Properties['sync_from_repo']) {
                $syncOn = [bool]$cap.sync_from_repo
            }
        } catch { }
    }
    if ($env:BOBIVERSE_SYNC_FROM_REPO -eq '1') { $syncOn = $true }
    elseif ($env:BOBIVERSE_SYNC_FROM_REPO -eq '0') { $syncOn = $false }
    if (-not $syncOn) {
        Write-Host 'INFO sync-skip sync_from_repo=off (config) FR #3289'
        exit 0
    }
}

function Resolve-BobiverseClone {
    $clone = $env:BOBIVERSE_REPO
    if ($clone -and (Test-Path -LiteralPath (Join-Path $clone '.git'))) { return [IO.Path]::GetFullPath($clone) }
    # t780u: the clone lives under the discovered ai root; other fixed disks' \ai\bobiverse are tried after it.
    $cands = @((Join-Path (Get-BobiverseAiRoot) 'bobiverse'))
    if (-not $env:BOB_AI_ROOT) {   # an explicit BOB_AI_ROOT means THAT root only
        foreach ($d in @(Get-BobiverseFixedDisks)) { $cands += (Join-Path ($d.Root + 'ai') 'bobiverse') }
    }
    foreach ($c in @($cands | Select-Object -Unique)) {
        # #70: a box without a D: drive threw "Cannot find drive 'D'" on every start
        $drive = $c.Substring(0, 2)
        if (-not (Test-Path -LiteralPath ($drive + '\') -ErrorAction SilentlyContinue)) { continue }
        if (Test-Path -LiteralPath (Join-Path $c '.git') -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

$git = Resolve-BobiverseGitExe
$pulled = $false
$clone = $null
$viaWorkTree = $false
$wtReason = ''

# FR #269: operator/UAT hook - recompose flat scripts from the current tree without service restart or fetch.
if ($ComposeOnly) {
    if (-not $Product) {
        $leaf = (Split-Path -Leaf $InstallRoot).ToLowerInvariant()
        if (@('bob', 'jeeves', 'airc') -contains $leaf) { $Product = $leaf }
    }
    $clone = $InstallRoot
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'common\scripts')) -and
        -not (Test-Path -LiteralPath (Join-Path $InstallRoot 'scripts'))) {
        Write-Host "WARN compose-only missing scripts under $InstallRoot"
        exit 1
    }
    $viaWorkTree = Test-Path -LiteralPath (Join-Path $InstallRoot '.git')
    Write-Host "INFO compose-only install=$InstallRoot product=$Product"
}

if (-not $ComposeOnly) {
# t781u/t782u source precedence:
#   1. BOBIVERSE_REPO (explicit dev override): that clone is ff'd and copied into the install tree (legacy behaviour).
#   2. the INSTALL DIR ITSELF as a sparse git work tree (<product>\ + common\ only): bootstrapped on first run, ff-only after.
#   3. a shared clone <ai root>obiverse - only when the work tree cannot be used (git missing / offline on first start).
$explicitRepo = ($env:BOBIVERSE_REPO -and (Test-Path -LiteralPath (Join-Path $env:BOBIVERSE_REPO '.git')))
if (-not $Product) {
    $leaf = (Split-Path -Leaf $InstallRoot).ToLowerInvariant()
    if (@('bob', 'jeeves', 'airc') -contains $leaf) { $Product = $leaf }
}
if (-not $explicitRepo -and $Product) {
    $wt = Sync-BobiverseWorkTree -InstallRoot $InstallRoot -Product $Product -Branch $Branch -GitExe $git -DryRun:$DryRun
    foreach ($l in @($wt.Log)) { Write-Host $l }
    $wtReason = [string]$wt.Reason
    Write-Host ("INFO sync-worktree ok={0} pulled={1} branch={2}: {3}" -f $wt.Ok, $wt.Pulled, $wt.Branch, $wtReason)
    # FR #1074 / #2470: surface stale fetch/ff/behind so operators notice offer gates may lag main.
    if ($wtReason -match 'timed out|ff-only not possible|fetch failed|not main|detached HEAD|still behind|behind origin') {
        Write-Host ("ALERT sync-worktree-stale: {0}" -f $wtReason)
    }
    if ($wt.Ok -and (Test-Path -LiteralPath (Join-Path $InstallRoot "$Product\scripts"))) {
        $clone = $InstallRoot
        $pulled = [bool]$wt.Pulled
        $viaWorkTree = $true
    }
}
if (-not $clone -and $DryRun -and -not $explicitRepo) { Write-Host 'INFO sync-dry-run done'; exit 0 }
if (-not $clone) { $clone = Resolve-BobiverseClone }
if (-not $clone) {
    Write-Host 'INFO sync-skip no usable work tree and no bobiverse clone (set BOBIVERSE_REPO or clone to <ai root>\bobiverse); keeping the installed files'
    exit 2
}
if (-not $git -and -not $viaWorkTree) {
    Write-Host "INFO sync-skip git.exe missing; will still copy from clone=$clone"
}

if ($git -and -not $viaWorkTree) {
    Write-Host "INFO sync-fetch clone=$clone branch=$Branch"
    if (-not $DryRun) {
        # git writes progress to stderr; do not let native stderr abort under Stop.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $fetchOut = & $git -C $clone fetch --prune origin 2>&1
            $fetchCode = $LASTEXITCODE
            foreach ($line in @($fetchOut)) { if ("$line".Trim()) { Write-Host "  $line" } }
            if ($fetchCode -ne 0) {
                Write-Host "WARN sync-fetch exit=$fetchCode (continuing with local clone tree)"
            } else {
                $head = (& $git -C $clone rev-parse --abbrev-ref HEAD 2>$null)
                if ($head -eq $Branch) {
                    $mergeOut = & $git -C $clone merge --ff-only "origin/$Branch" 2>&1
                    $mergeCode = $LASTEXITCODE
                    foreach ($line in @($mergeOut)) { if ("$line".Trim()) { Write-Host "  $line" } }
                    if ($mergeCode -eq 0) {
                        $pulled = $true
                        Write-Host "INFO sync-ff-only ok origin/$Branch"
                    } else {
                        Write-Host "WARN sync-ff-only failed (dirty or diverged); syncing current clone tree"
                    }
                } else {
                    Write-Host "WARN sync-skip-ff HEAD=$head (want $Branch); syncing current clone tree without checkout"
                }
            }
        } finally {
            $ErrorActionPreference = $prevEap
        }
    } else {
        Write-Host 'INFO sync-dry-run skip fetch/merge'
    }
}

}

# t773u: the clone may be a split repo (common\ jeeves\ bob\ airc\) or an older flat one; the INSTALL tree is always flat.
$verSrc = Get-BobiverseRepoPath -Root $clone -Rel 'src\VERSION'
if (-not (Test-Path -LiteralPath $verSrc)) { $verSrc = Join-Path $clone 'VERSION' }
$cloneVer = if (Test-Path -LiteralPath $verSrc) { (Get-Content -LiteralPath $verSrc -Raw).Trim() } else { '?' }
Write-Host "INFO sync-copy clone=$clone ver=$cloneVer -> $InstallRoot pulled=$pulled"

# FR #1018: do not robocopy an older clone over a newer MSI-installed VERSION (caused 0.1.21 -> 0.1.20 rollback).
# FR #1565: when ARP DisplayVersion is present, heal InstallRoot\VERSION to ARP and never let a newer
# clone VERSION (e.g. git 0.1.22) clobber the MSI-stamped file (ARP 0.1.21).
$installVerFile = Join-Path $InstallRoot 'VERSION'
$installVerText = if (Test-Path -LiteralPath $installVerFile) { (Get-Content -LiteralPath $installVerFile -Raw).Trim() } else { '' }
function ConvertTo-BobiverseVersion([string]$Text) {
    if ($Text -match '(\d+)\.(\d+)\.(\d+)') { return [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])" }
    return $null
}
function Get-BobiverseArpDisplayVersion([string]$ProductName) {
    # Match Update-BobiverseService Get-BobiverseArpProduct spelling; compare case-insensitive
    # so "Bobiverse airc" / "bobiverse airc" both hit (MRB #1577).
    $want = "bobiverse $($ProductName.Trim().ToLowerInvariant())"
    foreach ($root in @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
        )) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($k in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            try {
                $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop
                $dn = [string]$p.DisplayName
                if (-not $dn) { continue }
                if ($dn.Trim().ToLowerInvariant() -ne $want) { continue }
                $dv = [string]$p.DisplayVersion
                if ($dv) { return $dv.Trim() }
            } catch { }
        }
    }
    return ''
}
# Test hook: -ArpVersionOverride none|- means "no ARP row" (skip live registry).
$arpOverride = if ($ArpVersionOverride) { $ArpVersionOverride.Trim() } else { '' }
$arpVerText = if ($arpOverride -in @('none', '-', 'null')) {
    ''
} elseif ($arpOverride) {
    $arpOverride
} else {
    Get-BobiverseArpDisplayVersion -ProductName $Product
}
$arpVer = ConvertTo-BobiverseVersion $arpVerText
if ($arpVer) {
    $curFile = ConvertTo-BobiverseVersion $installVerText
    if (-not $curFile -or $curFile -ne $arpVer) {
        Set-Content -LiteralPath $installVerFile -Value ($arpVer.ToString() + [Environment]::NewLine) -Encoding ascii
        Write-Host ("INFO sync-heal-version-from-arp was={0} arp={1} (FR #1565)" -f $(if ($installVerText) { $installVerText } else { 'missing' }), $arpVer.ToString())
        $installVerText = $arpVer.ToString()
    }
}
$installVer = ConvertTo-BobiverseVersion $installVerText
$cloneVerObj = ConvertTo-BobiverseVersion $cloneVer
if ($installVer -and $cloneVerObj -and $installVer -gt $cloneVerObj) {
    Write-Host "WARN sync-skip-newer-install install=$($installVer.ToString()) clone=$($cloneVerObj.ToString()) - refusing to overwrite MSI tree with older clone"
    exit 0
}
# Remember ARP so the final VERSION copy can refuse a newer clone stamp.
$script:BobiverseArpVersion = $arpVer
$script:BobiverseSkipVersionCopyFromClone = $false
if ($arpVer -and $cloneVerObj -and $arpVer -ne $cloneVerObj) {
    $script:BobiverseSkipVersionCopyFromClone = $true
    Write-Host ("WARN sync-skip-arp-version ARP={0} clone={1} - MSI VERSION is source of truth (FR #1565)" -f $arpVer.ToString(), $cloneVerObj.ToString())
}

if ($DryRun) {
    Write-Host 'INFO sync-dry-run done'
    exit 0
}

# FR #2982: when the install dir is its own sparse work tree and ff/fetch left it
# dirty or behind origin, robocopy would re-lay that stale checkout over the MSI
# heat payload (scripts/tools/skills/worker). VERSION equality alone does not
# protect this (common\VERSION may be stamped to the MSI version - FR #2948 class).
# ComposeOnly is an operator hook after a manual ff - still compose.
# Tip updater overlay (FR #2581) still runs so Update-BobiverseService soft-fail lands.
$skipStaleCompose = $false
if ($viaWorkTree -and -not $ComposeOnly) {
    $tipOk = (
        $wtReason -eq 'already up to date' -or
        $wtReason -match '^fast-forwarded' -or
        $wtReason -match '^bootstrapped' -or
        $wtReason -match '^healed unborn'
    )
    if (-not $tipOk -and -not $pulled) {
        $skipStaleCompose = $true
        Write-Host ("ALERT sync-skip-stale-worktree: {0} - keeping installed (MSI) flat files; tip updater overlay still runs (FR #2982)" -f $wtReason)
    }
}

if (-not $skipStaleCompose) {
foreach ($d in @('scripts', 'third_party')) {
    $t = Join-Path $InstallRoot $d
    foreach ($s in @(Get-BobiverseRepoDirs -Root $clone -Sub $d)) {
        # FR #269: never /XO on scripts - git checkout mtimes are often older than the flat copy from a
        # previous compose, so /XO left scripts\gitclaim.py stale after ff-only.
        if ($d -eq 'scripts') {
            $roboArgs = @($s, $t, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np')
        } else {
            $roboArgs = @($s, $t, '/E', '/XO', '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np')
        }
        & robocopy.exe @roboArgs | Out-Null
        $rc = $LASTEXITCODE
        # robocopy 0-7 = success family
        if ($rc -ge 8) {
            Write-Host "WARN sync-robocopy $d exit=$rc"
        } else {
            Write-Host ("INFO sync-robocopy {0} ok{1}" -f $d, $(if ($d -eq 'scripts') { ' (forced, no /XO)' } else { '' }))
        }
    }
}
} # end -not $skipStaleCompose (scripts/third_party)

# FR #2581: when ff is blocked by dirty hotpatches, the robocopy above still
# copies a stale Update-BobiverseService.ps1. Overlay origin/<Branch> tip so
# #2563 soft-fail / ForceCheck escape reaches flat scripts\ without a clean ff.
# FR #2982: still run this overlay when skipStaleCompose (MSI flat files kept).
if (-not $DryRun -and $git -and (Test-Path -LiteralPath (Join-Path $InstallRoot '.git'))) {
    try {
        $upd = Sync-BobiverseUpdaterFromOrigin -InstallRoot $InstallRoot -Branch $Branch -GitExe $git
        if ($upd.Ok) {
            Write-Host ("INFO sync-updater-from-tip ok bytes={0}: {1}" -f $upd.Bytes, $upd.Reason)
        } else {
            Write-Host ("WARN sync-updater-from-tip skipped: {0}" -f $upd.Reason)
        }
    } catch {
        Write-Host ("WARN sync-updater-from-tip error: {0}" -f $_.Exception.Message)
    }
}

if (-not $skipStaleCompose) {
# t784u: runtime dirs the stage/MSI lays out under another name than the repo uses (the tray runs from tools\ src\ assets\, not
# from third_party\bob-tray; jeeves tools\). Without this a work-tree ff would update third_party\ but not what actually runs.
$mirror = @()
if ($Product -eq 'bob') {
    $mirror += @(
        @{ Rel = 'third_party\bob-tray\tools'; Dst = 'tools'; Xf = @() },
        @{ Rel = 'third_party\bob-tray\assets'; Dst = 'assets'; Xf = @() },
        @{ Rel = 'third_party\bob-tray\dialogs'; Dst = 'dialogs'; Xf = @() },
        @{ Rel = 'third_party\bob-tray\src'; Dst = 'src'; Xf = @('VERSION') },
        @{ Rel = 'third_party\Watch-AgentHealth'; Dst = 'Watch-AgentHealth'; Xf = @() })
}
if ($Product -eq 'jeeves') { $mirror += @{ Rel = 'tools'; Dst = 'tools'; Xf = @() } }
foreach ($m in $mirror) {
    $from = Get-BobiverseRepoPath -Root $clone -Rel $m.Rel
    if (-not (Test-Path -LiteralPath $from -PathType Container)) { continue }
    $roboArgs = @($from, (Join-Path $InstallRoot $m.Dst), '/E', '/XO', '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np')
    if ($m.Xf.Count) { $roboArgs += @('/XF') + $m.Xf }
    & robocopy.exe @roboArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Host ("WARN sync-robocopy {0} exit={1}" -f $m.Dst, $LASTEXITCODE) } else { Write-Host ("INFO sync-robocopy {0} ok" -f $m.Dst) }
}

# t828u: compile the Acknowledge/Status dialog exes into <install>\tools when missing or older than their sources (csc.exe is in-box on Windows;
# a running dialog is replaced by rename). Failure only warns: the tray then uses its PowerShell dialogs.
if ($Product -eq 'bob') {
    try {
        $dlgDir = Join-Path $InstallRoot 'dialogs'
        $dlgNewest = $null
        if (Test-Path -LiteralPath $dlgDir) { $dlgNewest = (Get-ChildItem -LiteralPath $dlgDir -File | Measure-Object LastWriteTimeUtc -Maximum).Maximum }
        $needBuild = $false
        foreach ($x in 'bob-about.exe', 'bob-status.exe', 'bob-tray.exe') {
            $xp = Join-Path $InstallRoot ('tools\' + $x)
            if (-not (Test-Path -LiteralPath $xp)) { $needBuild = $true }
            elseif ($dlgNewest -and (Get-Item -LiteralPath $xp).LastWriteTimeUtc -lt $dlgNewest) { $needBuild = $true }
        }
        $bd = Join-Path $InstallRoot 'scripts\Build-BobDialogs.ps1'
        if ($needBuild -and $dlgNewest -and (Test-Path -LiteralPath $bd)) {
            [void](& $bd -RepoRoot $InstallRoot -OutDir (Join-Path $InstallRoot 'tools') -SourceDir $dlgDir)
            Write-Host 'INFO sync compiled bob-about.exe + bob-status.exe + bob-tray.exe'
        }
    } catch { Write-Host ("WARN sync dialogs not compiled: {0}" -f $_.Exception.Message) }
}

# t794u: the tray no longer updates itself; drop the update scripts older installs still carry in tools\ (the sync never deletes).
if ($Product -eq 'bob') {
    foreach ($obsolete in 'Update-BobSystrayFromGit.ps1', 'Show-BobSystrayUpdatingDialog.ps1', 'Bootstrap-BobSystray.ps1') {
        $op = Join-Path $InstallRoot ('tools\' + $obsolete)
        if (Test-Path -LiteralPath $op) { Remove-Item -LiteralPath $op -Force -ErrorAction SilentlyContinue; Write-Host "INFO sync removed obsolete tray script $obsolete" }
    }
}

# Product skills book (shared harvest + product skill) when present in clone.
$skillsDirs = @(Get-BobiverseRepoDirs -Root $clone -Sub '.grok\skills')
$skillsDst = Join-Path $InstallRoot '.grok\skills'
if ($skillsDirs.Count -gt 0) {
    New-Item -ItemType Directory -Force -Path $skillsDst | Out-Null
    $bookNames = @($skillsDirs | ForEach-Object { Get-ChildItem -LiteralPath $_ -Directory -ErrorAction SilentlyContinue } |
            Where-Object { $_.Name -in @('harvest', 'harvest-agent-skills', 'bobiverse-fleet-ops') -or
                ($Product -and ($_.Name -eq "bobiverse-$Product" -or $_.Name -like "bobiverse-$Product-*")) } |
            ForEach-Object { $_.Name })
    foreach ($name in $bookNames) {
        $s = @($skillsDirs | ForEach-Object { Join-Path $_ $name } | Where-Object { Test-Path -LiteralPath $_ })[0]
        if ($s) {
            $t = Join-Path $skillsDst $name
            & robocopy.exe $s $t /E /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        }
    }
}

# t762u: bob worker\ + plan\ agent folders (skills + AGENTS; the exe only ever comes via the MSI; plan\work is never touched).
if ($Product -eq 'bob') {
    try {
        [void](Sync-BobiverseAgentFolders -RepoRoot $clone -Destination $InstallRoot)
    } catch { Write-Host ("WARN sync worker/plan folders: {0}" -f $_.Exception.Message) }
}

# Agent-start layer for this product (AGENTS.md / CLAUDE.md / GROK.md / .cursor rule) from AGENTS.<product>.md.
if ($Product) {
    $agentsSrc = Get-BobiverseRepoPath -Root $clone -Rel "AGENTS.$Product.md"
    if (Test-Path -LiteralPath $agentsSrc) {
        foreach ($d in @('AGENTS.md', 'CLAUDE.md', 'GROK.md')) { Copy-Item -Force -LiteralPath $agentsSrc -Destination (Join-Path $InstallRoot $d) }
        $ruleDir = Join-Path $InstallRoot '.cursor\rules'
        New-Item -ItemType Directory -Force -Path $ruleDir | Out-Null
        $mdc = "---`ndescription: Bobiverse $Product service briefing`nalwaysApply: true`n---`n`n" + [IO.File]::ReadAllText($agentsSrc)
        [IO.File]::WriteAllText((Join-Path $ruleDir "bobiverse-$Product.mdc"), $mdc, [Text.UTF8Encoding]::new($false))
        Write-Host "INFO sync-agent-layer AGENTS.md CLAUDE.md GROK.md .cursor/rules/bobiverse-$Product.mdc"
    }
    foreach ($docsSrc in @(Get-BobiverseRepoDirs -Root $clone -Sub 'docs')) {
        & robocopy.exe $docsSrc (Join-Path $InstallRoot 'docs') '*.md' /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    }
}
} # end -not $skipStaleCompose (mirror/skills/agent)

if (Test-Path -LiteralPath $verSrc) {
    if ($script:BobiverseSkipVersionCopyFromClone) {
        Write-Host 'INFO sync-keep-arp-version (skipped clone VERSION copy; FR #1565)'
    } else {
        Copy-Item -Force -LiteralPath $verSrc -Destination (Join-Path $InstallRoot 'VERSION')
    }
}

$localVer = '?'
$verFile = Join-Path $InstallRoot 'VERSION'
if (Test-Path -LiteralPath $verFile) { $localVer = (Get-Content -LiteralPath $verFile -Raw).Trim() }
Write-Host "INFO sync-done install=$InstallRoot version=$localVer"
exit 0
