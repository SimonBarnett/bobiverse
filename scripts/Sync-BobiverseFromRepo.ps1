#Requires -Version 5.1
<#
.SYNOPSIS
  Fast-forward the bobiverse git clone, then sync runtime files into a product install tree.
.DESCRIPTION
  Used by Start-Jeeves / Start-Bob / Start-AircConsole before launch.
  1) Resolve clone: BOBIVERSE_REPO, else C:\ai\bobiverse / D:\ai\bobiverse
  2) git fetch + merge --ff-only origin/main (best-effort; never blocks service start)
  3) Robocopy scripts + third_party into InstallRoot; copy VERSION
  Skips when BOBIVERSE_NO_UPDATE=1. Does not overwrite config\, home\, or secrets.
.PARAMETER Product
  jeeves | bob | airc — selects default InstallRoot C:\ai\<product>.
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

if (-not $InstallRoot) {
    if (-not $Product) { throw 'Sync-BobiverseFromRepo: pass -InstallRoot or -Product' }
    $InstallRoot = Join-Path 'C:\ai' $Product
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
if (-not (Test-Path -LiteralPath $InstallRoot)) {
    Write-Host "WARN sync-skip missing install root $InstallRoot"
    exit 1
}

function Resolve-BobiverseGitExe {
    foreach ($c in @(
            (Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
            (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
            (Join-Path $env:ProgramFiles 'Git\bin\git.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe'),
            (Join-Path $env:LOCALAPPDATA 'grok\git\2.55.0.windows.5\cmd\git.exe'),
            'C:\Users\medatech.si\AppData\Local\grok\git\2.55.0.windows.5\cmd\git.exe'
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Resolve-BobiverseClone {
    $clone = $env:BOBIVERSE_REPO
    if ($clone -and (Test-Path -LiteralPath (Join-Path $clone '.git'))) { return [IO.Path]::GetFullPath($clone) }
    foreach ($c in @('C:\ai\bobiverse', 'D:\ai\bobiverse')) {
        # #70: a box without a D: drive threw "Cannot find drive 'D'" on every start
        $drive = $c.Substring(0, 2)
        if (-not (Test-Path -LiteralPath ($drive + '\') -ErrorAction SilentlyContinue)) { continue }
        if (Test-Path -LiteralPath (Join-Path $c '.git') -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

$git = Resolve-BobiverseGitExe
$clone = Resolve-BobiverseClone
if (-not $clone) {
    Write-Host 'INFO sync-skip no bobiverse clone (set BOBIVERSE_REPO or use C:\ai\bobiverse)'
    exit 2
}
if (-not $git) {
    Write-Host "INFO sync-skip git.exe missing; will still copy from clone=$clone"
}

$pulled = $false
if ($git) {
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

$verSrc = Join-Path $clone 'src\VERSION'
if (-not (Test-Path -LiteralPath $verSrc)) { $verSrc = Join-Path $clone 'VERSION' }
$cloneVer = if (Test-Path -LiteralPath $verSrc) { (Get-Content -LiteralPath $verSrc -Raw).Trim() } else { '?' }
Write-Host "INFO sync-copy clone=$clone ver=$cloneVer -> $InstallRoot pulled=$pulled"

if ($DryRun) {
    Write-Host 'INFO sync-dry-run done'
    exit 0
}

foreach ($d in @('scripts', 'third_party')) {
    $s = Join-Path $clone $d
    $t = Join-Path $InstallRoot $d
    if (Test-Path -LiteralPath $s) {
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
$skillsSrc = Join-Path $clone '.grok\skills'
$skillsDst = Join-Path $InstallRoot '.grok\skills'
if (Test-Path -LiteralPath $skillsSrc) {
    New-Item -ItemType Directory -Force -Path $skillsDst | Out-Null
    $bookNames = @(Get-ChildItem -LiteralPath $skillsSrc -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in @('harvest', 'harvest-agent-skills', 'bobiverse-fleet-ops') -or
                ($Product -and ($_.Name -eq "bobiverse-$Product" -or $_.Name -like "bobiverse-$Product-*")) } |
            ForEach-Object { $_.Name })
    foreach ($name in $bookNames) {
        $s = Join-Path $skillsSrc $name
        if (Test-Path -LiteralPath $s) {
            $t = Join-Path $skillsDst $name
            & robocopy.exe $s $t /E /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        }
    }
}

# Agent-start layer for this product (AGENTS.md / CLAUDE.md / GROK.md / .cursor rule) from AGENTS.<product>.md.
if ($Product) {
    $agentsSrc = Join-Path $clone "AGENTS.$Product.md"
    if (Test-Path -LiteralPath $agentsSrc) {
        foreach ($d in @('AGENTS.md', 'CLAUDE.md', 'GROK.md')) { Copy-Item -Force -LiteralPath $agentsSrc -Destination (Join-Path $InstallRoot $d) }
        $ruleDir = Join-Path $InstallRoot '.cursor\rules'
        New-Item -ItemType Directory -Force -Path $ruleDir | Out-Null
        $mdc = "---`ndescription: Bobiverse $Product service briefing`nalwaysApply: true`n---`n`n" + [IO.File]::ReadAllText($agentsSrc)
        [IO.File]::WriteAllText((Join-Path $ruleDir "bobiverse-$Product.mdc"), $mdc, [Text.UTF8Encoding]::new($false))
        Write-Host "INFO sync-agent-layer AGENTS.md CLAUDE.md GROK.md .cursor/rules/bobiverse-$Product.mdc"
    }
    $docsSrc = Join-Path $clone 'docs'
    if (Test-Path -LiteralPath $docsSrc) {
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
