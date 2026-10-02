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
     never blocks service start, falls back to the installed files)
  3) Robocopy scripts + third_party + skills + docs into InstallRoot (never deleting); copy VERSION
  Skips when BOBIVERSE_NO_UPDATE=1. Does not overwrite config\, home\, or secrets.
.PARAMETER Product
  jeeves | bob | airc — selects default InstallRoot <ai root>\<product>.
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
    [switch]$DryRun
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
    Write-Host ("INFO sync-worktree ok={0} pulled={1} branch={2}: {3}" -f $wt.Ok, $wt.Pulled, $wt.Branch, $wt.Reason)
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

# t773u: the clone may be a split repo (common\ jeeves\ bob\ airc\) or an older flat one; the INSTALL tree is always flat.
$verSrc = Get-BobiverseRepoPath -Root $clone -Rel 'src\VERSION'
if (-not (Test-Path -LiteralPath $verSrc)) { $verSrc = Join-Path $clone 'VERSION' }
$cloneVer = if (Test-Path -LiteralPath $verSrc) { (Get-Content -LiteralPath $verSrc -Raw).Trim() } else { '?' }
Write-Host "INFO sync-copy clone=$clone ver=$cloneVer -> $InstallRoot pulled=$pulled"

if ($DryRun) {
    Write-Host 'INFO sync-dry-run done'
    exit 0
}

foreach ($d in @('scripts', 'third_party')) {
    $t = Join-Path $InstallRoot $d
    foreach ($s in @(Get-BobiverseRepoDirs -Root $clone -Sub $d)) {
        & robocopy.exe $s $t /E /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        $rc = $LASTEXITCODE
        # robocopy 0-7 = success family
        if ($rc -ge 8) {
            Write-Host "WARN sync-robocopy $d exit=$rc"
        } else {
            Write-Host "INFO sync-robocopy $d ok"
        }
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

if (Test-Path -LiteralPath $verSrc) {
    Copy-Item -Force -LiteralPath $verSrc -Destination (Join-Path $InstallRoot 'VERSION')
}

$localVer = '?'
$verFile = Join-Path $InstallRoot 'VERSION'
if (Test-Path -LiteralPath $verFile) { $localVer = (Get-Content -LiteralPath $verFile -Raw).Trim() }
Write-Host "INFO sync-done install=$InstallRoot version=$localVer"
exit 0
