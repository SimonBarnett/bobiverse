#Requires -Version 5.1
<#
.SYNOPSIS
  Stage + WiX-pack jeeves, bob, and/or airc MSIs for SimonBarnett/bobiverse releases.
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'jeeves', 'bob', 'airc')]
    [string]$Product = 'all',
    [string]$RepoRoot = '',
    [string]$OutDir = '',
    [string]$Version = '',
    [switch]$KeepStage,
    [switch]$SkipMsi,
    # Issue #4: bob/jeeves public GitHub Release MSIs must NOT embed the live Ergo PASS
    # unless -EmbedErgoPassword (private/offline). FR #4216: airc MSI ALWAYS embeds
    # config\ergo.password (required for first-start connect); -EmbedErgoPassword is
    # redundant for airc but still accepted.
    [switch]$EmbedErgoPassword,
    # Tests only (needs -SkipMsi): stage the worker/plan folders without compiling bob-worker.exe (PyInstaller, ~40 s).
    [switch]$SkipWorkerExe,
    # Tests only (needs -SkipMsi): skip bob-ear.exe (FR #1481 PyInstaller, ~40 s).
    [switch]$SkipEarExe,
    [switch]$SkipPriorityExe,
    # Tests only (needs -SkipMsi): skip skills-visionary PlanAgent.exe download (FR #9354); MZ stub / fixture.
    [switch]$SkipPlanAgentExe,
    # Tests only (needs -SkipMsi): skip jeeves.exe (FR #2301 / WP3 PyInstaller).
    [switch]$SkipJeevesExe,
    # Tests only (needs -SkipMsi): skip airc.exe (FR #2397 PyInstaller).
    [switch]$SkipAircExe,
    # Tests only (needs -SkipMsi): skip airc-network-installer.exe (FR #3991 PyInstaller + UAC).
    [switch]$SkipAircNetworkInstallerExe,
    # Tests only (needs -SkipMsi): skip Watch-AgentHealth.exe compile (FR #6603 stage gates).
    [switch]$SkipWatcherExe,
    # FR #9766: prebuilt CI artifacts. Release pack copies these and does not rebuild.
    [string]$TrayArtifactDir = '',
    [string]$StatusArtifactDir = '',
    [string]$WatcherArtifactDir = '',
    # FR #6423 / MRB #6427: test-only override for the published-release downgrade gate (requires -SkipMsi).
    [string]$LatestPublishedVersion = '',
    # FR #6423 / MRB #6427: skip GitHub latest comparison (requires -SkipMsi; release packs must not skip).
    [switch]$SkipPublishedVersionCheck
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Bobiverse-Common.ps1')
. (Join-Path $PSScriptRoot 'Bobiverse-FetchHelpers.ps1')
# t773u: the repo is split per service (common\ jeeves\ bob\ airc\); this script lives in common\scripts. The STAGE stays flat.
if (-not $RepoRoot) {
    $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $Version = (Get-Content (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION') -Raw).Trim()
}
# FR #4389: MSI Product/@Version is major.minor.build only; fold x.y.z.w -> x.y.(z+w) (1.0.0.1 -> 1.0.1).
$msiVersion = ConvertTo-BobiverseMsiProductVersion -Version $Version
# FR #6423: refuse packing a ProductVersion below the latest GitHub release (UAT/release path).
# -SkipMsi stage tests keep historical -Version pins (e.g. 0.1.99) and auto-skip this gate.
# Bypass switches are test-only: require -SkipMsi so a release MSI pack cannot skip the gate (MRB #6427).
if ($SkipPublishedVersionCheck -and -not $SkipMsi) {
    throw '-SkipPublishedVersionCheck is only allowed together with -SkipMsi (release packs must not skip FR #6423)'
}
if ($LatestPublishedVersion -and -not $SkipMsi) {
    throw '-LatestPublishedVersion is only allowed together with -SkipMsi (test override must not ship an MSI)'
}
if (-not $SkipPublishedVersionCheck -and -not $SkipMsi) {
    Assert-BobiversePackVersionNotDowngrade -Version $msiVersion -Repo 'SimonBarnett/bobiverse' -LatestPublishedVersion $LatestPublishedVersion
}

$fetchNssm = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Nssm.ps1')
$fetchWix = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Wix.ps1')
$fetchErgo = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Ergo.ps1')
$null = & $fetchNssm -OutDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm\win64') -CacheDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm')

if ($SkipWorkerExe -and -not $SkipMsi) { throw '-SkipWorkerExe is only allowed together with -SkipMsi (an MSI without bob-worker.exe must never ship)' }
if ($SkipEarExe -and -not $SkipMsi) { throw '-SkipEarExe is only allowed together with -SkipMsi (an MSI without bob-ear.exe must never ship; FR #1481)' }
if ($SkipPlanAgentExe -and -not $SkipMsi) { throw '-SkipPlanAgentExe is only allowed together with -SkipMsi (an MSI without PlanAgent.exe must never ship; FR #9354)' }
if ($SkipPriorityExe -and -not $SkipMsi) { throw '-SkipPriorityExe is only allowed together with -SkipMsi (an MSI without PriorityAgent.exe must never ship; FR #8701)' }
if ($SkipJeevesExe -and -not $SkipMsi) { throw '-SkipJeevesExe is only allowed together with -SkipMsi (an MSI without jeeves.exe must never ship; FR #2301)' }
if ($SkipAircExe -and -not $SkipMsi) { throw '-SkipAircExe is only allowed together with -SkipMsi (an MSI without airc.exe must never ship; FR #2397)' }
if ($SkipAircNetworkInstallerExe -and -not $SkipMsi) { throw '-SkipAircNetworkInstallerExe is only allowed together with -SkipMsi (an MSI without airc-network-installer.exe must never ship; FR #3991)' }
if ($SkipWatcherExe -and -not $SkipMsi) { throw '-SkipWatcherExe is only allowed together with -SkipMsi (an MSI without Watch-AgentHealth.exe must never ship; FR #6603)' }
if (-not $TrayArtifactDir -and $env:BOB_TRAY_ARTIFACT) { $TrayArtifactDir = $env:BOB_TRAY_ARTIFACT }
if (-not $StatusArtifactDir -and $env:BOB_STATUS_ARTIFACT) { $StatusArtifactDir = $env:BOB_STATUS_ARTIFACT }
if (-not $WatcherArtifactDir -and $env:BOB_WATCHER_ARTIFACT) { $WatcherArtifactDir = $env:BOB_WATCHER_ARTIFACT }

function Copy-BobPrebuiltExe {
    param(
        [string]$Dir,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Dest
    )
    $src = if ($Dir) { Join-Path $Dir $Name } else { '' }
    if (-not $src -or -not (Test-Path -LiteralPath $src)) { throw "missing $Name" }
    $destDir = Split-Path -Parent $Dest
    if ($destDir) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    Copy-Item -LiteralPath $src -Destination $Dest -Force
    Write-Host "INFO bob staged prebuilt $Name"
}

$products = if ($Product -eq 'all') { @('jeeves', 'bob', 'airc') } else { @($Product) }

function Resolve-WatchAgentHealthSrc {
    # FR #795: prefer bobiverse paths; do not fall back to archived agentic_build.
    foreach ($c in @(
            (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'bob\agentwatcher'),
            (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\Watch-AgentHealth'),
            $env:BOBIVERSE_WATCH_AGENTHEALTH
        )) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'Watch-AgentHealth.ps1'))) {
            return $c
        }
    }
    return $null
}

function Stage-BobAgentFolders([string]$Stage) {
    # t762u: bob MSI payload gains worker\ (bob-worker.exe + AGENTS/skills); plan\ is vendored (FR #8833 / #9354).
    # FR #1481: also stage scripts\bob-ear.exe (frozen irc_agent) so ircBob does not need system Python for the ear.
    $made = Sync-BobiverseAgentFolders -RepoRoot $RepoRoot -Destination $Stage
    if ($made -lt 1) { throw 'bob pack requires bob-agents\worker' }
    # FR #8700 / BOB-49: bob-ear (bob product) MSI must include Plan agent.
    # FR #9354: vendor PlanAgent.exe from SimonBarnett/skills-visionary releases (sha256 fail-closed).
    # FR #8833: bob/agents/plan source tree removed; ensure plan\ + pointer AGENTS.md for the stage.
    $planDir = Join-Path $Stage 'plan'
    New-Item -ItemType Directory -Force -Path $planDir | Out-Null
    $planAgents = Join-Path $planDir 'AGENTS.md'
    if (-not (Test-Path -LiteralPath $planAgents -PathType Leaf)) {
        $enc = New-Object System.Text.UTF8Encoding($false)
        $stub = @(
            '# Plan agent (vendored)'
            ''
            'Plan lives in https://github.com/SimonBarnett/skills-visionary (FR #8833).'
            'This folder is filled at pack time with PlanAgent.exe from the skills-visionary release (FR #9354 / BOB-49).'
            'Tray Plan starts a NEW plan agent every time (never resume).'
            ''
            '> **CAST IRON RULE - HARVEST AND FILE EVERYTHING**'
            '> File via intake webhook (`POST https://bob.ntsa.uk/bob/v1/intake`; offline queued/retried):'
            '> `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary -Kind issue -Title t -Body b`'
            '> `..\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary -Summary s -Lesson l`'
            ''
        ) -join [Environment]::NewLine
        [IO.File]::WriteAllText($planAgents, $stub + [Environment]::NewLine, $enc)
    }
    if (-not (Test-Path -LiteralPath $planDir -PathType Container)) {
        throw 'BOB-49: bob MSI stage missing plan\ (Plan agent build)'
    }
    if (-not (Test-Path -LiteralPath $planAgents -PathType Leaf)) {
        throw 'BOB-49: bob MSI stage plan\ missing AGENTS.md'
    }
    $planExe = Join-Path $planDir 'PlanAgent.exe'
    $planVendor = $null
    $planSrc = $null
    foreach ($c in @(
            [string]$env:BOB_PLAN_AGENT_EXE,
            (Join-Path $OutDir 'PlanAgent.exe')
        )) {
        if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { $planSrc = $c; break }
    }
    if ($SkipPlanAgentExe) {
        $fix = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'bob\tests\fixtures\PlanAgent.exe'
        if ($planSrc) {
            Copy-Item -LiteralPath $planSrc -Destination $planExe -Force
        } elseif (Test-Path -LiteralPath $fix -PathType Leaf) {
            Copy-Item -LiteralPath $fix -Destination $planExe -Force
        } else {
            [IO.File]::WriteAllBytes($planExe, [byte[]](0x4D, 0x5A))
        }
        $planVendor = @{
            tag = 'skip-test'
            sha256 = (Get-BobiverseFileSha256 -Path $planExe)
            bytes = [int64](Get-Item -LiteralPath $planExe).Length
            repo = 'local-skip'
            asset = 'PlanAgent.exe'
            url = ''
            path = $planExe
        }
        Write-Host 'WARN bob pack: -SkipPlanAgentExe (test stage PlanAgent.exe stub)'
    } elseif ($planSrc) {
        Copy-Item -LiteralPath $planSrc -Destination $planExe -Force
        $planVendor = @{
            tag = 'local'
            sha256 = (Get-BobiverseFileSha256 -Path $planExe)
            bytes = [int64](Get-Item -LiteralPath $planExe).Length
            repo = 'local'
            asset = 'PlanAgent.exe'
            url = $planSrc
            path = $planExe
        }
        Write-Host ("INFO bob staged plan\PlanAgent.exe from {0}" -f $planSrc)
    } else {
        $planTag = [string]$env:BOB_PLAN_AGENT_RELEASE_TAG
        $cache = Join-Path $OutDir 'vendor\skills-visionary'
        $planVendor = Save-BobiverseGhReleaseVerifiedExe `
            -Repo 'SimonBarnett/skills-visionary' `
            -AssetName 'PlanAgent.exe' `
            -Destination $planExe `
            -Tag $planTag `
            -CacheDir $cache `
            -TimeoutSec 900
    }
    if (-not (Test-Path -LiteralPath $planExe -PathType Leaf)) {
        throw 'BOB-49 / FR #9354: bob MSI stage missing plan\PlanAgent.exe'
    }
    $planMan = Join-Path $planDir 'PlanAgent.MANIFEST.json'
    # Capture void: helper must not pollute Stage-Product success stream (MRB #9358 / FR #6969).
    $null = Write-BobiverseVendoredExeManifest -Path $planMan -Info $planVendor -Fr '9354' -Bob 'BOB-49'
    $marker = Join-Path $Stage 'plan\BOB-49-PLAN-IN-MSI.txt'
    $markerBody = @(
        'bob=BOB-49'
        'fr=8700'
        'fr_vendor=9354'
        'slice=bob-ear-msi-include-plan'
        'path=plan\'
        'plan_agent=plan\PlanAgent.exe'
        ('plan_agent_repo={0}' -f $planVendor.repo)
        ('plan_agent_tag={0}' -f $planVendor.tag)
        ('plan_agent_sha256={0}' -f $planVendor.sha256)
        ('plan_agent_bytes={0}' -f $planVendor.bytes)
        'heat=include-plan'
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($marker, $markerBody + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ("INFO bob staged plan\ + PlanAgent.exe for bob-ear MSI (BOB-49 / FR #8700 / #9354 tag={0})" -f $planVendor.tag)
    # FR #8675 / BOB-10: stamp plan\VERSION from MSI-aligned pack identity.
    $planCommit = ''
    try { $planCommit = [string](& git -C $RepoRoot rev-parse --short HEAD 2>$null | Select-Object -First 1) } catch { }
    Write-BobiversePlanIdentity -Destination $Stage -Version $msiVersion -Commit $planCommit.Trim()
    # FR #8701 / BOB-55: bob-ear MSI must include PriorityAgent.exe.
    # FR #9354: prefer SimonBarnett/priority-mcp release download+sha256 (env/OutDir override; Skip for tests).
    $priDir = Join-Path $Stage 'priority'
    New-Item -ItemType Directory -Force -Path $priDir | Out-Null
    $priExe = Join-Path $priDir 'PriorityAgent.exe'
    $priVendor = $null
    $priSrc = $null
    foreach ($c in @(
            [string]$env:BOB_PRIORITY_AGENT_EXE,
            (Join-Path $OutDir 'PriorityAgent.exe')
        )) {
        if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { $priSrc = $c; break }
    }
    if ($SkipPriorityExe) {
        $fix = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'bob\tests\fixtures\PriorityAgent.exe'
        if ($priSrc) {
            Copy-Item -LiteralPath $priSrc -Destination $priExe -Force
        } elseif (Test-Path -LiteralPath $fix -PathType Leaf) {
            Copy-Item -LiteralPath $fix -Destination $priExe -Force
        } else {
            [IO.File]::WriteAllBytes($priExe, [byte[]](0x4D, 0x5A))
        }
        $priVendor = @{
            tag = 'skip-test'
            sha256 = (Get-BobiverseFileSha256 -Path $priExe)
            bytes = [int64](Get-Item -LiteralPath $priExe).Length
            repo = 'local-skip'
            asset = 'PriorityAgent.exe'
            url = ''
            path = $priExe
        }
        Write-Host 'WARN bob pack: -SkipPriorityExe (test stage PriorityAgent.exe stub)'
    } elseif ($priSrc) {
        Copy-Item -LiteralPath $priSrc -Destination $priExe -Force
        $priVendor = @{
            tag = 'local'
            sha256 = (Get-BobiverseFileSha256 -Path $priExe)
            bytes = [int64](Get-Item -LiteralPath $priExe).Length
            repo = 'local'
            asset = 'PriorityAgent.exe'
            url = $priSrc
            path = $priExe
        }
        Write-Host ("INFO bob staged priority\PriorityAgent.exe from {0}" -f $priSrc)
    } else {
        $priTag = [string]$env:BOB_PRIORITY_AGENT_RELEASE_TAG
        $cache = Join-Path $OutDir 'vendor\priority-mcp'
        $priVendor = Save-BobiverseGhReleaseVerifiedExe `
            -Repo 'SimonBarnett/priority-mcp' `
            -AssetName 'PriorityAgent.exe' `
            -Destination $priExe `
            -Tag $priTag `
            -CacheDir $cache `
            -TimeoutSec 900
    }
    if (-not (Test-Path -LiteralPath $priExe -PathType Leaf)) {
        throw 'BOB-55: bob MSI stage missing priority\PriorityAgent.exe'
    }
    $priMan = Join-Path $priDir 'PriorityAgent.MANIFEST.json'
    $null = Write-BobiverseVendoredExeManifest -Path $priMan -Info $priVendor -Fr '9354' -Bob 'BOB-55'
    $priMarker = Join-Path $priDir 'BOB-55-PRIORITY-IN-MSI.txt'
    $priBody = @(
        'bob=BOB-55'
        'fr=8701'
        'fr_vendor=9354'
        'slice=bob-ear-msi-include-priority'
        'path=priority\PriorityAgent.exe'
        ('priority_agent_repo={0}' -f $priVendor.repo)
        ('priority_agent_tag={0}' -f $priVendor.tag)
        ('priority_agent_sha256={0}' -f $priVendor.sha256)
        ('priority_agent_bytes={0}' -f $priVendor.bytes)
        'heat=include-PriorityAgent'
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($priMarker, $priBody + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ("INFO bob staged priority\PriorityAgent.exe for bob-ear MSI (BOB-55 / FR #8701 / #9354 tag={0})" -f $priVendor.tag)
    # FR #9468 / #9598: mirror PlanAgent + PriorityAgent into vendor\; never stage bob-plan.exe.
    # TipForm Agents > Plan uses vendor\plan\PlanAgent.exe (FR #9605 / #9641). Release sources:
    # skills-visionary plan-* / priority-mcp launcher-*.
    $null = Copy-BobTrayVendorExes -Root $Stage -Require
    if (-not (Test-Path -LiteralPath (Join-Path $Stage 'vendor\plan\PlanAgent.exe') -PathType Leaf)) {
        throw 'FR #9468/#9598: bob MSI stage missing vendor\plan\PlanAgent.exe'
    }
    if (Test-Path -LiteralPath (Join-Path $Stage 'vendor\plan\bob-plan.exe') -PathType Leaf) {
        throw 'FR #9598: bob MSI stage must not include vendor\plan\bob-plan.exe (PlanAgent.exe only)'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Stage 'vendor\priority\PriorityAgent.exe') -PathType Leaf)) {
        throw 'FR #9468: bob MSI stage missing vendor\priority\PriorityAgent.exe'
    }


    if ($SkipWorkerExe) {
        Write-Host 'WARN bob pack: -SkipWorkerExe (test stage; no bob-worker.exe)'
    } else {
        $buildWorker = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-BobWorker.ps1')
        $exe = (& $buildWorker -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
        if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { throw 'Build-BobWorker.ps1 did not produce bob-worker.exe' }
        Copy-Item -LiteralPath $exe -Destination (Join-Path $Stage 'worker\bob-worker.exe') -Force
        # FR #7910: frozen resolver reads <exe dir>\scripts, never the _MEI extract.
        $shipDir = Join-Path (Split-Path -Parent $exe) 'scripts'
        if (-not (Test-Path -LiteralPath $shipDir)) { throw 'bob pack missing worker\scripts from Build-BobWorker.ps1' }
        $shipDest = Join-Path $Stage 'worker\scripts'
        New-Item -ItemType Directory -Force -Path $shipDest | Out-Null
        Copy-Item -Path (Join-Path $shipDir '*') -Destination $shipDest -Force
        Write-Host 'INFO bob staged worker\bob-worker.exe and worker\scripts'
        # FR #9641: after worker lands, refuse identical bytes under PlanAgent (Workers seat via Agents > Plan).
        # FR #9843: Assert returns a Hashtable - capture or heat Stage becomes
        # "System.Collections.Hashtable <path>" (FR #6969 resurfaced).
        $null = Assert-BobiversePlanAgentNotBobWorker -Root $Stage -Require
    }
    if ($SkipEarExe) {
        Write-Host 'WARN bob pack: -SkipEarExe (test stage; no bob-ear.exe)'
    } else {
        $buildEar = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-BobEar.ps1')
        if (-not (Test-Path -LiteralPath $buildEar)) { throw "missing Build-BobEar.ps1 (FR #1481): $buildEar" }
        $ear = (& $buildEar -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
        if (-not $ear -or -not (Test-Path -LiteralPath $ear)) { throw 'Build-BobEar.ps1 did not produce bob-ear.exe' }
        $earDest = Join-Path $Stage 'scripts\bob-ear.exe'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $earDest) | Out-Null
        Copy-Item -LiteralPath $ear -Destination $earDest -Force
        Write-Host 'INFO bob staged scripts\bob-ear.exe (FR #1481)'
    }
}

function Assert-BobiverseStageHasOpencodeFuel([string]$Stage) {
    # Get-BobOpencodeFuel imports flat scripts\opencode_fuel.py. A stage without it
    # installs a tray that cannot read OpenCode fuel. Fail before the MSI is built.
    $ocFuel = Join-Path $Stage 'scripts\opencode_fuel.py'
    if (-not (Test-Path -LiteralPath $ocFuel -PathType Leaf)) {
        throw 'bobiverse pack missing scripts\opencode_fuel.py (common\scripts union)'
    }
}

function Assert-BobiverseStageHasSkillDagMcp([string]$Stage) {
    # FR #9136: chair/monitor seats resolve skills via install scripts\skill_dag_mcp.py
    # (not a borrowed C:\ai\bob path). Fail pack when the union omitted the trio.
    foreach ($name in @('skill_dag_mcp.py', 'skill_dag_index.py', 'skill_dag_bound.py')) {
        $p = Join-Path $Stage ("scripts\$name")
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
            throw ("bobiverse pack missing scripts\{0} (bob\scripts union; FR #9136)" -f $name)
        }
    }
}

function Assert-BobiverseStageHasModelsRefresh([string]$Stage) {
    # FR #9224: BobCallback imports flat scripts\models_refresh.py for POST
    # /bob/v1/models/refresh. A stage without it installs a chair that 404s refresh.
    $mr = Join-Path $Stage 'scripts\models_refresh.py'
    if (-not (Test-Path -LiteralPath $mr -PathType Leaf)) {
        throw 'bobiverse pack missing scripts\models_refresh.py (common\scripts union)'
    }
}


function Stage-Product([string]$Name) {
    $stage = Join-Path $OutDir ("$Name-$Version")
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force -Path "$stage\scripts", "$stage\docs", "$stage\.grok\skills", "$stage\src", "$stage\config", "$stage\third_party\nssm\win64" | Out-Null
    # t773u: the flat staged scripts\ is the UNION of common\scripts + jeeves\scripts + bob\scripts + airc\scripts.
    Copy-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts' -Dest (Join-Path $stage 'scripts')
    # Flat scripts\opencode_fuel.py comes from common\scripts (Get-BobOpencodeFuel import).
    Assert-BobiverseStageHasOpencodeFuel -Stage $stage
    # FR #9136: skill-dag MCP trio from bob\scripts must land in every product stage scripts\.
    Assert-BobiverseStageHasSkillDagMcp -Stage $stage
    # Flat scripts\models_refresh.py comes from common\scripts (BobCallback POST refresh).
    Assert-BobiverseStageHasModelsRefresh -Stage $stage
    # Issue #2: do not ship __pycache__ (self-copy / heat noise)
    Get-ChildItem -Path (Join-Path $stage 'scripts') -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    # FR #3686 / FR #4389: stage VERSION from MSI ProductVersion (3-part fold of pack -Version).
    # never by copying common\VERSION alone. A release pack with -Version 0.1.27 while
    # common\VERSION still said 0.1.25 shipped BUILD.json=0.1.27 + VERSION=0.1.25 (walrus).
    $verUtf8 = New-Object Text.UTF8Encoding $false
    $verText = $msiVersion.Trim() + [Environment]::NewLine
    [IO.File]::WriteAllText((Join-Path $stage 'VERSION'), $verText, $verUtf8)
    [IO.File]::WriteAllText((Join-Path $stage 'src\VERSION'), $verText, $verUtf8)
    # t797u: BUILD.json = what the tray About dialog shows as version / build date / commit for this install folder.
    $buildCommit = ''
    $buildCommitFull = ''
    try { $buildCommit = [string](& git -C $RepoRoot rev-parse --short HEAD 2>$null | Select-Object -First 1) } catch { }
    try { $buildCommitFull = [string](& git -C $RepoRoot rev-parse HEAD 2>$null | Select-Object -First 1) } catch { }
    ([ordered]@{ product = $Name; version = $msiVersion; release_version = $Version; built_utc = [datetime]::UtcNow.ToString('o'); commit = $buildCommit.Trim() } |
        ConvertTo-Json -Compress) | Set-Content -LiteralPath (Join-Path $stage 'BUILD.json') -Encoding ascii
    # FR #3686: pack fails closed if VERSION / BUILD.json / ProductVersion disagree.
    Assert-BobiverseStageVersionAligned -Stage $stage -ExpectedVersion $msiVersion -Product $Name
    # FR #6924: MANIFEST.json + provenance for tray label (MSI VERSION stays; short SHA from source).
    if ($Name -eq 'bob' -and $buildCommitFull -match '^[0-9a-fA-F]{7,40}$') {
        $idWriter = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Write-BobTrayDeployedIdentity.ps1'
        if (Test-Path -LiteralPath $idWriter) {
            & $idWriter -InstallRoot $stage -Commit $buildCommitFull.Trim() -Builder 'Pack-BobiverseRelease.ps1' | Out-Null
        }
    }

    # Product AGENTS.md (repo AGENTS.<product>.md -> stage AGENTS.md)
    $agentsSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel "AGENTS.$Name.md"
    if (Test-Path -LiteralPath $agentsSrc) {
        Copy-Item -LiteralPath $agentsSrc -Destination (Join-Path $stage 'AGENTS.md') -Force
        # Agent-start layer: the same briefing under every agent's well-known name, so Grok / Claude / Cursor started in
        # the install dir all begin with FULL service information (and the CAST IRON harvest rule).
        Copy-Item -LiteralPath $agentsSrc -Destination (Join-Path $stage 'CLAUDE.md') -Force
        Copy-Item -LiteralPath $agentsSrc -Destination (Join-Path $stage 'GROK.md') -Force
        $ruleDir = Join-Path $stage '.cursor\rules'
        New-Item -ItemType Directory -Force -Path $ruleDir | Out-Null
        $mdc = "---`ndescription: Bobiverse $Name service briefing (architecture, ops, hotpatch rules, CAST IRON harvest rule)`nalwaysApply: true`n---`n`n" + [IO.File]::ReadAllText($agentsSrc)
        [IO.File]::WriteAllText((Join-Path $ruleDir "bobiverse-$Name.mdc"), $mdc, [Text.UTF8Encoding]::new($false))
        Write-Host "INFO $Name staged AGENTS.md CLAUDE.md GROK.md .cursor/rules/bobiverse-$Name.mdc from AGENTS.$Name.md"
    } else {
        Write-Host "WARN $Name missing AGENTS.$Name.md (stage has no AGENTS.md)"
    }

    # Docs: shared map + product-named files + optional docs/<product>/ tree
        $docsDest = Join-Path $stage 'docs'
    $sharedDocs = @('post-install.md', 'skill-harvest-log.md', 'vision.md')
    $productDocsMap = @{
        'jeeves' = @('jeeves-admin.md', 'jeeves-commands.md', 'channel-privileges-and-workers.md', 'webhooks.md', 'jira-webhook-customer-guide.md')
        'bob'    = @('bob-ear.md')
        'airc'   = @('airc-ops.md', 'airc-remote-control.md')
    }
    $docsToCopy = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($d in $sharedDocs) { [void]$docsToCopy.Add($d) }
    foreach ($d in @($productDocsMap[$Name])) { if ($d) { [void]$docsToCopy.Add($d) } }
    foreach ($d in $docsToCopy) {
        $from = Get-BobiverseRepoPath -Root $RepoRoot -Rel "docs\$d"
        if (Test-Path -LiteralPath $from) {
            Copy-Item -LiteralPath $from -Destination (Join-Path $docsDest $d) -Force
        }
    }
    $productDocsDir = Get-BobiverseRepoPath -Root $RepoRoot -Rel "docs\$Name"
    if (Test-Path -LiteralPath $productDocsDir) {
        Copy-Item -Path (Join-Path $productDocsDir '*') -Destination $docsDest -Recurse -Force
        Write-Host "INFO $Name staged docs/$Name/ into docs\"
    }
    Write-Host ("INFO $Name staged docs: {0}" -f (($docsToCopy | Sort-Object) -join ', '))

    # Skills: product skill + harvest only (do not ship sibling product skills).
    # FR #9180: staged skills come from the pack RepoRoot checkout (merged main /
    # release tip). Harvest lessons reach MSI only after their lesson(<book>) PR
    # merges --- agent harvest must owe that skill PR, not receipt-only.
    $skillsDirs = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub '.grok\skills')
    function Find-RepoSkill([string]$n) { foreach ($sd in $skillsDirs) { $c = Join-Path $sd $n; if (Test-Path -LiteralPath $c) { return $c } } return (Join-Path $skillsDirs[0] $n) }
    $skillsDest = Join-Path $stage '.grok\skills'
    # This product's whole skill book: bobiverse-<p> + bobiverse-<p>-commands / -troubleshooting / ... + the shared fleet-ops book.
    $productSkill = "bobiverse-$Name"
    # FR #954: jeeves also stages monitor-start (first-turn auto-start skill).
    # FR #6159 / #6660: bob also stages bob-setup-opencode (OpenCode setup; mirror Sync-BobiverseFromRepo).
    $bookDirs = @($skillsDirs | ForEach-Object { Get-ChildItem -LiteralPath $_ -Directory -ErrorAction SilentlyContinue } |
            Where-Object {
                $_.Name -eq $productSkill -or $_.Name -like "$productSkill-*" -or $_.Name -eq 'bobiverse-fleet-ops' -or
                ($Name -eq 'jeeves' -and $_.Name -eq 'monitor-start') -or
                ($Name -eq 'bob' -and $_.Name -eq 'bob-setup-opencode')
            })
    if (-not ($bookDirs | Where-Object { $_.Name -eq $productSkill })) {
        Write-Host "WARN $Name missing .grok/skills/$productSkill"
    }
    foreach ($bd in $bookDirs) {
        New-Item -ItemType Directory -Force -Path (Join-Path $skillsDest $bd.Name) | Out-Null
        Copy-Item -Path (Join-Path $bd.FullName '*') -Destination (Join-Path $skillsDest $bd.Name) -Recurse -Force
    }
    Write-Host ("INFO $Name staged skill books: {0}" -f (($bookDirs | ForEach-Object Name) -join ', '))
    $harvestSrc = Find-RepoSkill 'harvest'
    $harvestAliasSrc = Find-RepoSkill 'harvest-agent-skills'
    if (Test-Path -LiteralPath $harvestSrc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $skillsDest 'harvest') | Out-Null
        Copy-Item -Path (Join-Path $harvestSrc '*') -Destination (Join-Path $skillsDest 'harvest') -Recurse -Force
    } elseif (Test-Path -LiteralPath $harvestAliasSrc) {
        # Alias: stage harvest-agent-skills content as harvest/
        New-Item -ItemType Directory -Force -Path (Join-Path $skillsDest 'harvest') | Out-Null
        Copy-Item -Path (Join-Path $harvestAliasSrc '*') -Destination (Join-Path $skillsDest 'harvest') -Recurse -Force
        Write-Host "INFO $Name staged harvest-agent-skills as harvest/"
    }
    if (Test-Path -LiteralPath $harvestAliasSrc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $skillsDest 'harvest-agent-skills') | Out-Null
        Copy-Item -Path (Join-Path $harvestAliasSrc '*') -Destination (Join-Path $skillsDest 'harvest-agent-skills') -Recurse -Force
    }
    # FR #9180: optional pin --- staged harvest book must include SKILL.md from merged tip.
    $stagedHarvestSkill = Join-Path $skillsDest 'harvest\SKILL.md'
    if (-not (Test-Path -LiteralPath $stagedHarvestSkill -PathType Leaf)) {
        Write-Host ("WARN FR #9180 $Name stage missing harvest/SKILL.md under {0} (live skills come from merged bobiverse .grok/skills)" -f $skillsDest)
    } else {
        Write-Host "INFO FR #9180 $Name staged harvest/SKILL.md (merged skill book present)"
    }

    # Bobiverse systray icon: every product's Start Menu shortcuts use it (bob also gets it via the tray payload).
    $trayIcoSrc = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets\bob-systray.ico')
    if (Test-Path -LiteralPath $trayIcoSrc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'assets') | Out-Null
        Copy-Item -LiteralPath $trayIcoSrc -Destination (Join-Path $stage 'assets\bob-systray.ico') -Force
    } else {
        Write-Host 'WARN third_party/bob-tray/assets/bob-systray.ico missing - Start Menu shortcuts fall back to default icons'
    }
    # FR #9211: OpenCode seat console icon (find_window_icon kind=opencode + launch-opencode.ps1).
    # FR #9267: stage all non-Cursor tray menu glyphs under assets\ for TipForm / Watch-BobTray.
    $stageAssets = Join-Path $stage 'assets'
    New-Item -ItemType Directory -Force -Path $stageAssets | Out-Null
    foreach ($menuIco in @(
            'opencode-favicon.ico',
            'grok-favicon.ico',
            'plan-gantt.ico',
            'priority.ico',
            'jeeves-butler.ico'
        )) {
        $srcIco = Get-BobiverseRepoPath -Root $RepoRoot -Rel ("bob\tray\assets\$menuIco")
        if (-not $srcIco -or -not (Test-Path -LiteralPath $srcIco)) {
            $srcIco = Get-BobiverseRepoPath -Root $RepoRoot -Rel ("third_party\bob-tray\assets\$menuIco")
        }
        if ($menuIco -eq 'opencode-favicon.ico' -and (-not $srcIco -or -not (Test-Path -LiteralPath $srcIco))) {
            $srcIco = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets\opencode-favicon.ico'
        }
        if ($srcIco -and (Test-Path -LiteralPath $srcIco)) {
            Copy-Item -LiteralPath $srcIco -Destination (Join-Path $stageAssets $menuIco) -Force
            Write-Host ("INFO FR #9267/#9211 staged assets\{0}" -f $menuIco)
        } else {
            Write-Host ("WARN FR #9267 menu icon missing: {0}" -f $menuIco)
        }
    }

    Copy-Item (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm\win64\nssm.exe') (Join-Path $stage 'third_party\nssm\win64\nssm.exe') -Force
    # Issue #4: bob/jeeves public packs skip Ergo PASS unless -EmbedErgoPassword.
    # FR #4216: airc MSI MUST ship config\ergo.password so install connects on first start.
    # FR #4349: !build pack uses isolated USERPROFILE and blanks AGENTIC/BOB_IRC; also search
    # live fleet installs via Get-BobiverseAiRoot and BOB_IRC_PASSWORD / AIRC_PACK inject.
    $stageErgo = Join-Path $stage 'config\ergo.password'
    New-Item -ItemType Directory -Force -Path (Join-Path $stage 'config') | Out-Null
    $wantEmbedErgo = $EmbedErgoPassword -or ($Name -eq 'airc')
    # FR #4477: -SkipMsi is a test stage, not a release MSI. Do not copy a live
    # Ergo PASS or write a placeholder password file into that stage. Real airc
    # packs (no -SkipMsi) still embed config\ergo.password (FR #4216).
    if ($SkipMsi) { $wantEmbedErgo = $false }
    if ($wantEmbedErgo) {
        $ergoSecret = $null
        $ergoSource = $null
        if ($Name -eq 'airc') {
            foreach ($key in @('AIRC_PACK_ERGO_PASSWORD', 'AGENTIC_IRC_PASSWORD', 'AIRC_CONSOLE_SERVER_PASSWORD', 'BOB_IRC_PASSWORD')) {
                $v = [Environment]::GetEnvironmentVariable($key)
                if ($v -and $v.Trim()) {
                    $ergoSecret = $v.Trim()
                    $ergoSource = "env:$key"
                    break
                }
            }
        }
        if (-not $ergoSecret) {
            $aiRoot = $null
            try { $aiRoot = Get-BobiverseAiRoot } catch { $aiRoot = $null }
            $cand = @(
                (Join-Path $RepoRoot 'config\ergo.password'),
                (Join-Path $env:USERPROFILE '.grok\ergo\connect.password'),
                (Join-Path $env:USERPROFILE '.grok\ergo\ergo.password')
            )
            if ($aiRoot) {
                foreach ($prod in @('bob', 'airc', 'jeeves')) {
                    $cand += (Join-Path $aiRoot "$prod\config\ergo.password")
                }
            }
            foreach ($c in $cand) {
                if ($c -and (Test-Path -LiteralPath $c)) {
                    $raw = (Get-Content -LiteralPath $c -Raw -ErrorAction SilentlyContinue)
                    if ($raw -and $raw.Trim()) {
                        $ergoSecret = $raw.Trim()
                        $ergoSource = $c
                        break
                    }
                }
            }
        }
        if (-not $ergoSecret) {
            if ($Name -eq 'airc') {
                throw 'airc pack requires Ergo server PASS for config/ergo.password (FR #4216/#4349): set AIRC_PACK_ERGO_PASSWORD / AGENTIC_IRC_PASSWORD / AIRC_CONSOLE_SERVER_PASSWORD / BOB_IRC_PASSWORD, or pack on a box with ~/.grok/ergo/connect.password, repo config\ergo.password, or <ai root>\bob|airc|jeeves\config\ergo.password'
            }
            throw '-EmbedErgoPassword set but no config/ergo.password or ~/.grok/ergo/connect.password found'
        }
        [IO.File]::WriteAllText($stageErgo, $ergoSecret + "`n", [Text.UTF8Encoding]::new($false))
        Write-Host ("INFO {0} embedded config/ergo.password from {1} (len={2}; value not printed){3}" -f $Name, $ergoSource, $ergoSecret.Length, $(if ($Name -eq 'airc') { ' FR #4216' } else { ' (-EmbedErgoPassword)' }))
    } else {
        if (Test-Path -LiteralPath $stageErgo) {
            Remove-Item -LiteralPath $stageErgo -Force
            Write-Host "WARN $Name removed staged config/ergo.password (issue #4 public pack guard)"
        }
        if ($SkipMsi) {
            Write-Host "INFO $Name -SkipMsi: not embedding config/ergo.password (FR #4477; not a release artifact)"
        } else {
            Write-Host "INFO $Name skipping Ergo PASS embed (issue #4; pass -EmbedErgoPassword for private packs)"
        }
    }
    if ($Name -eq 'jeeves') {
        $ergoStage = Join-Path $stage 'ergo'
        New-Item -ItemType Directory -Force -Path $ergoStage | Out-Null
        $null = & $fetchErgo -OutDir $ergoStage -CacheDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\ergo')
        if (-not (Test-Path -LiteralPath (Join-Path $ergoStage 'ergo.exe'))) {
            throw 'jeeves pack requires ergo.exe (Fetch-Ergo failed)'
        }
        # Optional operator ircd.yaml (never from git secrets); else Install seeds default.yaml
        foreach ($c in @(
                (Join-Path $RepoRoot 'config\ircd.yaml'),
                $env:BOBIVERSE_IRCD_YAML,
                (Join-Path (Get-BobiverseAiRoot) 'ergo\ircd.yaml')   # t780u: discovered ai root
            )) {
            if ($c -and (Test-Path -LiteralPath $c)) {
                Copy-Item -LiteralPath $c -Destination (Join-Path $ergoStage 'ircd.yaml') -Force
                Write-Host "INFO jeeves embedded ergo/ircd.yaml from $c"
                break
            }
        }
        Write-Host "INFO jeeves staged Ergo payload under ergo\"
        # #53: webhook helpers shipped with the receiver (git hook ensure/verify + repo hook creator)
        $toolsStage = Join-Path $stage 'tools'
        New-Item -ItemType Directory -Force -Path $toolsStage | Out-Null
        foreach ($tf in @('bob_git_hook.py', 'New-BobGitWebhook.ps1')) {
            $from = Get-BobiverseRepoPath -Root $RepoRoot -Rel "tools\$tf"
            if (-not (Test-Path -LiteralPath $from)) { throw "jeeves pack requires tools\$tf (webhooks, #53)" }
            Copy-Item -LiteralPath $from -Destination (Join-Path $toolsStage $tf) -Force
        }
        Write-Host "INFO jeeves staged tools\bob_git_hook.py + New-BobGitWebhook.ps1"
        # FR #787: token-free MONITORING checks + butler Start Menu icon
        $monSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\tools\monitor'
        if (-not (Test-Path -LiteralPath $monSrc)) { throw 'jeeves pack requires jeeves\tools\monitor (FR #787)' }
        $monDest = Join-Path $toolsStage 'monitor'
        New-Item -ItemType Directory -Force -Path $monDest | Out-Null
        Copy-Item -Path (Join-Path $monSrc '*') -Destination $monDest -Recurse -Force
        Write-Host "INFO jeeves staged tools\monitor (FR #787)"
        $butlerSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\assets\jeeves-butler.ico'
        if (-not (Test-Path -LiteralPath $butlerSrc)) { throw 'jeeves pack requires jeeves\assets\jeeves-butler.ico (FR #787)' }
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'assets') | Out-Null
        Copy-Item -LiteralPath $butlerSrc -Destination (Join-Path $stage 'assets\jeeves-butler.ico') -Force
        Write-Host "INFO jeeves staged assets\jeeves-butler.ico"
        # FR #4725: fleet resync-repos.txt defaults (includes ce-priority) for Install fallback
        $resyncSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\defaults\resync-repos.txt'
        if (-not (Test-Path -LiteralPath $resyncSrc)) { throw 'jeeves pack requires jeeves\defaults\resync-repos.txt (FR #4725)' }
        $defaultsDest = Join-Path $stage 'defaults'
        New-Item -ItemType Directory -Force -Path $defaultsDest | Out-Null
        Copy-Item -LiteralPath $resyncSrc -Destination (Join-Path $defaultsDest 'resync-repos.txt') -Force
        Write-Host 'INFO jeeves staged defaults\resync-repos.txt (FR #4725)'
        # BOB-04 / FR #8709: seed for models-valid-combos.json (fail-closed allow-list)
        $seedSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'common\defaults\models-valid-combos.seed.json'
        if (-not (Test-Path -LiteralPath $seedSrc)) { throw 'jeeves pack requires common\defaults\models-valid-combos.seed.json (FR #8709)' }
        Copy-Item -LiteralPath $seedSrc -Destination (Join-Path $defaultsDest 'models-valid-combos.seed.json') -Force
        Write-Host 'INFO jeeves staged defaults\models-valid-combos.seed.json (FR #8709)'
        # FR #7455: publish jeeves/www beside flat scripts so Install-BobWebhooks ..\www\irc-ntsa works from MSI layout.
        $wwwSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\www'
        if (-not (Test-Path -LiteralPath $wwwSrc)) { throw 'jeeves pack requires jeeves\www (FR #7455)' }
        $wwwDest = Join-Path $stage 'www'
        New-Item -ItemType Directory -Force -Path $wwwDest | Out-Null
        Copy-Item -Path (Join-Path $wwwSrc '*') -Destination $wwwDest -Recurse -Force
        Write-Host 'INFO jeeves staged www from jeeves\www (FR #7455)'
        # FR #2301 / WP3: one-file jeeves.exe (chair + in-proc HTTP)
        $jeevesExeDir = Join-Path $stage 'jeeves'
        New-Item -ItemType Directory -Force -Path $jeevesExeDir | Out-Null
        if ($SkipJeevesExe) {
            Write-Host 'WARN jeeves pack: -SkipJeevesExe (test stage; no jeeves.exe)'
        } else {
            $buildJeeves = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-Jeeves.ps1')
            if (-not (Test-Path -LiteralPath $buildJeeves)) { throw "missing Build-Jeeves.ps1 (FR #2301): $buildJeeves" }
            $jexe = (& $buildJeeves -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
            if (-not $jexe -or -not (Test-Path -LiteralPath $jexe)) { throw 'Build-Jeeves.ps1 did not produce jeeves.exe' }
            Copy-Item -LiteralPath $jexe -Destination (Join-Path $jeevesExeDir 'jeeves.exe') -Force
            Write-Host 'INFO jeeves staged jeeves\jeeves.exe'
        }
    }
    if ($Name -eq 'bob') {
        $wahSrc = Resolve-WatchAgentHealthSrc
        if ($wahSrc) {
            $wahDest = Join-Path $stage 'Watch-AgentHealth'
            New-Item -ItemType Directory -Force -Path $wahDest | Out-Null
            Copy-Item -Path (Join-Path $wahSrc '*') -Destination $wahDest -Recurse -Force
            # Drop binary .lnk shortcuts from foreign trees (recreated by Install if needed)
            Get-ChildItem -Path $wahDest -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
            if ($SkipWatcherExe) {
                Write-Host 'WARN bob pack: -SkipWatcherExe (test stage; no Watch-AgentHealth.exe)'
            } else {
                # FR #9766: do not call Build-BobWatcher.ps1 on the release path.
                Copy-BobPrebuiltExe -Dir $WatcherArtifactDir -Name 'Watch-AgentHealth.exe' -Dest (Join-Path $wahDest 'Watch-AgentHealth.exe')
            }
            Write-Host "INFO bob staged Watch-AgentHealth from $wahSrc"
        } else {
            Write-Host 'WARN bob pack: Watch-AgentHealth source missing (Desktop install will skip)'
        }

        # t829u: the systray (bob\tray) is a first-class bob source -> InstallRoot tools/src/assets (flat)
        $traySrc = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray')
        if (-not (Test-Path -LiteralPath (Join-Path $traySrc 'tools\Watch-BobTray.ps1'))) {
            throw 'bob pack requires bob/tray/tools/Watch-BobTray.ps1 (first-class bob source, t829u)'
        }
        foreach ($sub in @('tools', 'assets')) {
            $from = Join-Path $traySrc $sub
            $to = Join-Path $stage $sub
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
        }
        # t828u: compiled Acknowledge/Status dialogs -> stage\tools\bob-about.exe, bob-status.exe (+ sources in stage\dialogs, rebuildable by Sync)
        $dlgSrc = Join-Path $traySrc 'dialogs'
        if (Test-Path -LiteralPath $dlgSrc) {
            New-Item -ItemType Directory -Force -Path (Join-Path $stage 'dialogs') | Out-Null
            Copy-Item -Path (Join-Path $dlgSrc '*') -Destination (Join-Path $stage 'dialogs') -Recurse -Force
            # FR #9766: stage prebuilt dialog exes. Do not call Build-BobDialogs.ps1.
            $toolsOut = Join-Path $stage 'tools'
            Copy-BobPrebuiltExe -Dir $TrayArtifactDir -Name 'bob-tray.exe' -Dest (Join-Path $toolsOut 'bob-tray.exe')
            Copy-BobPrebuiltExe -Dir $TrayArtifactDir -Name 'bob-about.exe' -Dest (Join-Path $toolsOut 'bob-about.exe')
            Copy-BobPrebuiltExe -Dir $StatusArtifactDir -Name 'bob-status.exe' -Dest (Join-Path $toolsOut 'bob-status.exe')
        } else { throw 'bob pack requires bob/tray/dialogs (t828u compiled dialogs)' }
        # Merge BobBridge module into stage\src (keep bobiverse VERSION)
        $traySrcDir = Join-Path $traySrc 'src'
        Copy-Item -LiteralPath (Join-Path $traySrcDir 'BobBridge.psd1') -Destination (Join-Path $stage 'src\BobBridge.psd1') -Force
        Copy-Item -LiteralPath (Join-Path $traySrcDir 'BobBridge.psm1') -Destination (Join-Path $stage 'src\BobBridge.psm1') -Force
        foreach ($sub in @('Public', 'Private')) {
            $from = Join-Path $traySrcDir $sub
            $to = Join-Path $stage "src\$sub"
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
        }
        Copy-Item -LiteralPath (Join-Path $traySrc 'PIN.txt') -Destination (Join-Path $stage 'PIN.txt') -Force
        foreach ($cfg in @('bobiverse.json', 'bob-seats.json', 'default.json', 'fleet-registry.json')) {
            $from = Join-Path $traySrc "config\$cfg"
            if (Test-Path -LiteralPath $from) {
                Copy-Item -LiteralPath $from -Destination (Join-Path $stage "config\$cfg") -Force
            }
        }
        # Guard: never ship ergo.password from tray sync
        $stageErgoGuard = Join-Path $stage 'config\ergo.password'
        if ((-not $EmbedErgoPassword) -and (Test-Path -LiteralPath $stageErgoGuard)) {
            Remove-Item -LiteralPath $stageErgoGuard -Force
        }
        # FR #9843: never let Stage-BobAgentFolders success-stream objects join into $stage.
        $null = Stage-BobAgentFolders -Stage $stage
        Write-Host ("INFO bob staged TipForm tray from {0} pin={1}" -f $traySrc, ((Get-Content (Join-Path $traySrc 'PIN.txt') -TotalCount 1).Trim()))
    }
    if ($Name -eq 'airc') {
        # FR #2397: one-file airc.exe (console service; no system Python on target)
        $aircExeDir = Join-Path $stage 'airc'
        New-Item -ItemType Directory -Force -Path $aircExeDir | Out-Null
        if ($SkipAircExe) {
            Write-Host 'WARN airc pack: -SkipAircExe (test stage; no airc.exe)'
        } else {
            $buildAirc = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-Airc.ps1')
            if (-not (Test-Path -LiteralPath $buildAirc)) { throw "missing Build-Airc.ps1 (FR #2397): $buildAirc" }
            $aexe = (& $buildAirc -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
            if (-not $aexe -or -not (Test-Path -LiteralPath $aexe)) { throw 'Build-Airc.ps1 did not produce airc.exe' }
            Copy-Item -LiteralPath $aexe -Destination (Join-Path $aircExeDir 'airc.exe') -Force
            Write-Host 'INFO airc staged airc\airc.exe'
        }
        # FR #5283 / #5905 / #5946: service-owned Priority Web SDK worker (not PriorityClient.exe).
        # Pack must include run-repprep + run-formprep + run-formwalk mjs + node_modules/priority-web-sdk so
        # prepare/walk find them without AIRC_PRIORITY_*_MJS or drop\.
        $pwSrc = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'priority-worker'
        if (-not (Test-Path -LiteralPath $pwSrc)) {
            $pwSrc = Join-Path $RepoRoot 'airc\priority-worker'
        }
        if (Test-Path -LiteralPath $pwSrc) {
            $mjsSrc = Join-Path $pwSrc 'sdk\run-repprep-via-exec.mjs'
            if (-not (Test-Path -LiteralPath $mjsSrc)) {
                throw 'airc pack requires airc/priority-worker/sdk/run-repprep-via-exec.mjs (FR #5905)'
            }
            $walkMjsSrc = Join-Path $pwSrc 'sdk\run-formwalk-readonly.mjs'
            if (-not (Test-Path -LiteralPath $walkMjsSrc)) {
                throw 'airc pack requires airc/priority-worker/sdk/run-formwalk-readonly.mjs (FR #5948)'
            }
            $formMjsSrc = Join-Path $pwSrc 'sdk\run-formprep-via-eform.mjs'
            if (-not (Test-Path -LiteralPath $formMjsSrc)) {
                throw 'airc pack requires airc/priority-worker/sdk/run-formprep-via-eform.mjs (FR #5946)'
            }
            # FR #5913: always npm ci so a stale/partial node_modules cannot ship
            # a priority-web-sdk that drifts from package-lock.json.
            $nm = Join-Path $pwSrc 'node_modules\priority-web-sdk'
            # FR #6975: -SkipMsi is a skill-layer stage test, not a release MSI.
            # BUILD isolation may have no npm; do not fail agent-layer [airc].
            $skipNpmCi = [bool]$SkipMsi
            if ($skipNpmCi) {
                Write-Host 'WARN airc pack: -SkipMsi skip npm ci (FR #6975 stage-only; release packs still npm ci)'
            } else {
                $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
                if (-not $npmCmd) {
                    throw 'airc pack: npm not on PATH (required for priority-worker npm ci; FR #5905/#5913)'
                }
                Write-Host 'INFO airc priority-worker: npm ci --omit=dev (FR #5905/#5913)'
                Push-Location -LiteralPath $pwSrc
                try {
                    # FR #6969: capture npm stdout. Native stdout in Stage-Product becomes
                    # extra function output; [string]$Stage then joins "npm notice ... https://..."
                    # and heat.exe HEAT0001 "path format is not supported".
                    # FR #6980: script EAP is Stop; npm writes "npm notice" on stderr.
                    # 2>&1 then wraps that as NativeCommandError / RemoteException.
                    $eapNpm = $ErrorActionPreference
                    $ErrorActionPreference = 'Continue'
                    try {
                        $npmOut = @(& npm ci --omit=dev --no-fund --no-audit 2>&1 | ForEach-Object { [string]$_ })
                        $npmExit = $LASTEXITCODE
                    } finally {
                        $ErrorActionPreference = $eapNpm
                    }
                    foreach ($line in $npmOut) { Write-Host $line }
                    if ($npmExit -ne 0) { throw "npm ci failed exit=$npmExit (FR #5905/#5913)" }
                } finally {
                    Pop-Location
                }
                if (-not (Test-Path -LiteralPath $nm)) {
                    throw 'airc pack: npm ci did not produce node_modules/priority-web-sdk (FR #5905/#5913)'
                }
            }
            $pwDest = Join-Path $aircExeDir 'priority-worker'
            New-Item -ItemType Directory -Force -Path $pwDest | Out-Null
            # FR #6079: sdk/priority-web-sdk/index.js is the test fixture for op names.
            # The runtime package is node_modules/priority-web-sdk from npm ci above.
            Get-ChildItem -LiteralPath $pwSrc -Force | Where-Object {
                $_.Name -ne '__pycache__'
            } | ForEach-Object {
                if ($_.Name -eq 'sdk') {
                    $sdkDest = Join-Path $pwDest 'sdk'
                    New-Item -ItemType Directory -Force -Path $sdkDest | Out-Null
                    Get-ChildItem -LiteralPath $_.FullName -Force | Where-Object {
                        $_.Name -ne 'priority-web-sdk'
                    } | ForEach-Object {
                        Copy-Item -LiteralPath $_.FullName -Destination $sdkDest -Recurse -Force
                    }
                } else {
                    Copy-Item -LiteralPath $_.FullName -Destination $pwDest -Recurse -Force
                }
            }
            # FR #6978: SkipMsi may skip npm ci, but client allowlist / heat still need
            # airc\priority-worker\node_modules\priority-web-sdk on the stage. Seed a
            # stage-only stub (never mutate the repo tree). Release packs use real npm ci.
            $nmDest = Join-Path $pwDest 'node_modules\priority-web-sdk'
            if ($skipNpmCi -and -not (Test-Path -LiteralPath $nmDest)) {
                New-Item -ItemType Directory -Force -Path $nmDest | Out-Null
                $stubPkg = Join-Path $nmDest 'package.json'
                Set-Content -LiteralPath $stubPkg -Value '{"name":"priority-web-sdk","private":true,"version":"0.0.0-skipmsi"}' -Encoding ascii
                $stubIdx = Join-Path $nmDest 'index.js'
                Set-Content -LiteralPath $stubIdx -Value 'module.exports = {}; // FR #6978 SkipMsi stub' -Encoding ascii
                Write-Host 'WARN airc pack: -SkipMsi seeded stub node_modules/priority-web-sdk (FR #6978)'
            }
            Write-Host 'INFO airc staged airc\priority-worker (FR #5283/#5905)'
        } else {
            throw 'airc pack requires airc/priority-worker (FR #5283)'
        }
        # FR #3991: elevated network-wide installer (UAC admin). Laid at INSTALLDIR root so
        # <ai root>\airc\airc-network-installer.exe can be re-run from any airc box; always
        # downloads Latest airc MSI (not the version it shipped with). Also emit versioned
        # release assets airc-network-installer-<ver>.exe + .sha256 next to the MSI.
        if ($SkipAircNetworkInstallerExe) {
            Write-Host 'WARN airc pack: -SkipAircNetworkInstallerExe (test stage; no airc-network-installer.exe)'
        } else {
            $buildNet = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-AircNetworkInstaller.ps1')
            if (-not (Test-Path -LiteralPath $buildNet)) { throw "missing Build-AircNetworkInstaller.ps1 (FR #3991): $buildNet" }
            $nexe = (& $buildNet -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
            if (-not $nexe -or -not (Test-Path -LiteralPath $nexe)) { throw 'Build-AircNetworkInstaller.ps1 did not produce airc-network-installer.exe' }
            Copy-Item -LiteralPath $nexe -Destination (Join-Path $stage 'airc-network-installer.exe') -Force
            Write-Host 'INFO airc staged airc-network-installer.exe (FR #3991)'
            $verExe = Join-Path $OutDir ("airc-network-installer-$Version.exe")
            Copy-Item -LiteralPath $nexe -Destination $verExe -Force
            $nhash = (Get-FileHash -LiteralPath $verExe -Algorithm SHA256).Hash.ToLower()
            Set-Content -LiteralPath ($verExe + '.sha256') -Value ("$nhash  airc-network-installer-$Version.exe") -Encoding ascii
            Write-Host ("INFO release asset airc-network-installer-{0}.exe sha256={1}" -f $Version, $nhash)
        }
        # FR #3639: no config\fleet-operators.txt roster - airc auth is live control-channel +o/+h.
    }
    return $stage
}

function Assert-BobiverseHeatStagePath {
    param(
        # FR #9843: accept object so Hashtable leaks are rejected before [string] join.
        [Parameter(Mandatory)]$Stage
    )
    # FR #6969: heat.exe DirectoryHarvester rejects URIs / "npm notice" blobs
    # when Stage-Product leaked native stdout into $stage.
    # FR #9843: Hashtable / multi-object success-stream leaks become
    # "System.Collections.Hashtable <path>" under [string] coercion.
    if ($null -eq $Stage) { throw 'FR #6969: heat stage path is empty' }
    if ($Stage -is [System.Collections.IDictionary] -or $Stage -is [hashtable]) {
        throw 'FR #6969/#9843: heat stage path is a Hashtable (Stage-Product success-stream leak; capture helper output with $null =).'
    }
    if ($Stage -is [System.Array] -or ($Stage -is [System.Collections.IList] -and -not ($Stage -is [string]))) {
        throw 'FR #6969/#9843: heat stage path is a list/array (Stage-Product success-stream leak; capture helper output with $null =).'
    }
    if ($Stage -isnot [string] -and $Stage -isnot [System.IO.DirectoryInfo]) {
        $tn = $Stage.GetType().FullName
        throw "FR #6969/#9843: heat stage path is not a string path (type=$tn); capture Stage-Product helper output."
    }
    $t = if ($Stage -is [System.IO.DirectoryInfo]) { [string]$Stage.FullName } else { [string]$Stage }
    if ([string]::IsNullOrWhiteSpace($t)) { throw 'FR #6969: heat stage path is empty' }
    if ($t -match '://' -or $t -match '(?i)npm notice' -or $t -match '(?i)System\.Collections\.Hashtable') {
        throw 'FR #6969: heat stage path is not a directory (native command stdout leaked into Stage-Product; capture npm ci / helper Hashtable).'
    }
    if (-not (Test-Path -LiteralPath $t -PathType Container)) {
        $shown = $t
        if ($shown.Length -gt 180) { $shown = $shown.Substring(0, 180) }
        throw "FR #6969: heat stage is not a directory: $shown"
    }
}

function Build-Msi([string]$Name, [string]$Stage) {
    if ($SkipMsi) {
        Write-Host "INFO SkipMsi stage=$Stage"
        return
    }
    $wixBin = & $fetchWix -CacheDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\wix')
    $candle = Join-Path $wixBin 'candle.exe'
    $light = Join-Path $wixBin 'light.exe'
    $heat = Join-Path $wixBin 'heat.exe'
    $util = Join-Path $wixBin 'WixUtilExtension.dll'
    $wixWork = Join-Path $OutDir ("wix-$Name-$Version")
    if (Test-Path $wixWork) { Remove-Item -Recurse -Force $wixWork }
    New-Item -ItemType Directory -Force -Path $wixWork | Out-Null

    $installDirName = $Name
    # t780u: the install dir is NOT baked in. An immediate JScript CA (common\packaging\FindAiRoot.js) sets AIROOT from the FIXED disks
    # at install time; INSTALLDIR = [AIROOT]\<product>. msiexec ... AIROOT=D:\ai overrides. Nothing is created unless no fixed disk has \ai.
    $findAiJs = [IO.File]::ReadAllText((Get-BobiverseRepoPath -Root $RepoRoot -Rel 'packaging\FindAiRoot.js')).TrimStart([char]0xFEFF)
    $findAiFile = Join-Path $wixWork 'FindAiRoot.js'
    [IO.File]::WriteAllText($findAiFile, $findAiJs, [Text.UTF8Encoding]::new($false))
    $cg = "Bobiverse$($Name)Files"
    $harvested = Join-Path $wixWork 'HarvestedFiles.wxs'
    Assert-BobiverseHeatStagePath -Stage $Stage
    & $heat dir $Stage -cg $cg -gg -sfrag -srd -sreg -scom -dr INSTALLDIR -var var.StageDir -out $harvested
    if ($LASTEXITCODE -ne 0) { throw "heat failed $LASTEXITCODE" }

    # #70 (v0.1.19) / FR #3899: the pack's nssm.exe is the service binary of running Windows services
    # (ircJeeves/ircBob, and on older boxes also BobIrcd/Ergo). heat used to mint a fresh component GUID every
    # build, so MajorUpgrade removed and re-laid nssm.exe (services holding it stopped / Ergo bounced).
    # Permanent + a stable per-product GUID keep the SAME component across releases so later uninstalls /
    # same-GUID upgrades do not thrash the file.
    # FR #3899: do NOT set NeverOverwrite on nssm. With MajorUpgrade Schedule=afterInstallInitialize,
    # CostFinalize marks NeverOverwrite files "skip install" while the old copy still exists; then
    # RemoveExistingProducts FileRemoves the pre-stable-GUID component; InstallFiles never FileCopys.
    # Flamingo 0.1.11 -> 0.1.30: nssm.exe gone, Install-AircConsole "nssm missing", msiexec 1603.
    # Permanent alone + stable GUID is enough once the file is laid; nssm 2.24 bytes are identical.
    [xml]$hx = Get-Content -LiteralPath $harvested -Raw -Encoding UTF8
    $wns = New-Object System.Xml.XmlNamespaceManager($hx.NameTable)
    $wns.AddNamespace('w', 'http://schemas.microsoft.com/wix/2006/wi')
    $nssmFiles = @($hx.SelectNodes('//w:File', $wns) | Where-Object { ([string]$_.GetAttribute('Source')) -match '[\\/]nssm\.exe$' })
    if ($nssmFiles.Count -lt 1) { throw 'nssm.exe component not found in harvested files (cannot mark it permanent)' }
    foreach ($nf in $nssmFiles) {
        $nc = $nf.ParentNode
        $nc.SetAttribute('Permanent', 'yes')
        if ($nc.HasAttribute('NeverOverwrite')) { [void]$nc.RemoveAttribute('NeverOverwrite') }
        # Stable component GUID (per product) so every release refers to the SAME component, not a fresh one.
        $nc.SetAttribute('Guid', '{' + ([guid]::new([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes("bobiverse-$Name-nssm-component"))).ToString().ToUpper()) + '}')
    }
    # FR #3686: unversioned VERSION files follow create/modify-date rules; a hand-touched
    # older install keeps stale VERSION across MajorUpgrade. RemoveFile On=install on the
    # same component deletes the target before the new file is laid.
    $verFiles = @($hx.SelectNodes('//w:File', $wns) | Where-Object {
            $srcAttr = [string]$_.GetAttribute('Source')
            $srcAttr -match '(?i)[\\/]VERSION$'
        })
    $rmIdx = 0
    foreach ($vf in $verFiles) {
        $vc = $vf.ParentNode
        $rm = $hx.CreateElement('RemoveFile', 'http://schemas.microsoft.com/wix/2006/wi')
        $rmIdx++
        $rm.SetAttribute('Id', ("RmStaleVersion{0}" -f $rmIdx))
        $rm.SetAttribute('Name', 'VERSION')
        $rm.SetAttribute('On', 'install')
        [void]$vc.AppendChild($rm)
    }
    if ($verFiles.Count -lt 1) {
        throw 'FR #3686: no VERSION File entries in harvested WiX (cannot force overwrite)'
    }
    Write-Host ("INFO FR #3686 RemoveFile On=install on {0} VERSION component(s)" -f $verFiles.Count)
    # #70 (v0.1.20): the same for ergo\ergo.exe. <ai root>\ergo\ergo.exe was found HARD-LINKED to the pack's
    # <ai root>\jeeves\ergo\ergo.exe, so the MSI rewriting its own copy rewrote the running Ergo binary and Windows
    # Restart Manager bounced BobIrcd (pid change, every client reconnected). The pack keeps shipping ergo.exe (fresh
    # installs seed <ai root>\ergo from it) but an upgrade must never remove/rewrite an existing one: Ergo upgrades are
    # deliberate (Install-BobIrcd -ForceErgo), never a side effect of a jeeves MSI.
    if ($Name -eq 'jeeves') {
        $ergoFiles = @($hx.SelectNodes('//w:File', $wns) | Where-Object { ([string]$_.GetAttribute('Source')) -match '[\\/]ergo[\\/]ergo\.exe$' })
        if ($ergoFiles.Count -lt 1) { throw 'ergo\ergo.exe component not found in harvested files (cannot mark it permanent)' }
        foreach ($ef in $ergoFiles) {
            $ec = $ef.ParentNode
            $ec.SetAttribute('Permanent', 'yes')
            $ec.SetAttribute('NeverOverwrite', 'yes')
            $ec.SetAttribute('Guid', '{' + ([guid]::new([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes("bobiverse-$Name-ergo-component"))).ToString().ToUpper()) + '}')
        }
        Write-Host ("INFO marked {0} ergo.exe component(s) Permanent+NeverOverwrite" -f $ergoFiles.Count)
    }
    # FR #3687 / #3740: airc agent briefings/skills/launchers live in BobiverseAircAgentLayerFiles
    # (AgentLayerFeature Condition Level=0 for client|workstation|AIRC_AGENT_LAYER=0).
    # heat puts Components under DirectoryRef and ComponentRef under the group - move refs
    # (Move-BobiverseAircMsiAgentLayerComponents). Fail closed when 0 match (FR #3740).
    # Report-BobiverseIntakeIssue.ps1 stays in the main group (client allow-list).
    $agentCg = $null
    if ($Name -eq 'airc') {
        $agentCg = 'BobiverseAircAgentLayerFiles'
        [void](Move-BobiverseAircMsiAgentLayerComponents -HarvestXml $hx -NamespaceManager $wns `
                -MainGroupId $cg -AgentGroupId $agentCg -FailIfNone)
    }
    $hx.Save($harvested)
    Write-Host ("INFO marked {0} nssm.exe component(s) Permanent+stable GUID (no NeverOverwrite; FR #3899)" -f $nssmFiles.Count)

    # airc UpgradeCode must NOT match agentic_irc airc-console
    # (B7E3C9A1-4F2D-4E8B-9C11-A1BC00501E01) or 0.1.x packs look like
    # downgrades of airc-console 0.1.19+ (issue #12).
    $upgrade = switch ($Name) {
        'jeeves' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC00FEE001' }
        'bob' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC0000B0B1' }
        'airc' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC00A1C001' }
    }
    $installCmd = switch ($Name) {
        'jeeves' { 'Install-Jeeves.cmd' }
        'bob' { 'Install-Bob.cmd' }
        'airc' { 'Install-Airc.cmd' }
    }
    # #70: public MSI properties flow into RunInstall (CAQuietExec64). Empty props expand to "" and Install-*.ps1 ignores them.
    # msiexec /i jeeves-*.msi OPERFILE=C:\path\oper.txt SKIPERGO=1 SKIPCOPY=1
    # msiexec /i bob-*.msi MACHINEID=marchhare SKIPCOPY=1
    # FR #2564: forward ProductVersion so Install-*.ps1 can Assert-BobiverseInstallVersion (no silent VERSION lie).
    $installArgs = switch ($Name) {
        'jeeves' {
            # FR #3290: BOBIVERSE_SKIP_TOOLS=1 skips Install-BootstrapTools.
            # FR #3291: BOBIVERSE_CRASH_REPORT opt-out (empty = fleet default on / prior config).
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -OperFile &quot;[OPERFILE]&quot; -OperName &quot;[OPERNAME]&quot; -OpAccounts &quot;[OPACCOUNTS]&quot; -MsiSkipErgo &quot;[SKIPERGO]&quot; -MsiSkipCopy &quot;[SKIPCOPY]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot; -CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;'
        }
        'bob' {
            # FR #3290 / #3291: skip-tools + crash-report MSI props.
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -MachineId &quot;[MACHINEID]&quot; -IrcHost &quot;[IRCHOST]&quot; -MsiSkipCopy &quot;[SKIPCOPY]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot; -CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;'
        }
        'airc' {
            # FR #3287: capability + account MSI props (empty = installer defaults / prior identity).
            # FR #3639: AIRC_OPERATORS retired (no operators list; control-channel +o/+h auth).
            # FR #3289: AIRC_SYNC_FROM_REPO / AIRC_SELF_UPDATE (empty = fresh sync off / self_update on, or keep prior).
            # FR #3290: AIRC_INSTALL_TOOLS=1 opts into git/gh/python/node bootstrap (default skip when airc.exe present).
            # FR #3292: AIRC_PROFILE=workstation / AIRC_AGENT_LAYER=0 skips agent briefings/skills.
            # FR #3291: BOBIVERSE_CRASH_REPORT (empty = preserve / shell=off => crash-report.json enabled=false).
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -MachineId &quot;[MACHINEID]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -ShellMode &quot;[AIRC_SHELL]&quot; -Jobs &quot;[AIRC_JOBS]&quot; -UpdateCap &quot;[AIRC_UPDATE]&quot; -ExtensionCap &quot;[AIRC_EXTENSION]&quot; -RequireAccount &quot;[AIRC_REQUIRE_ACCOUNT]&quot; -Accounts &quot;[AIRC_ACCOUNTS]&quot; -SyncFromRepo &quot;[AIRC_SYNC_FROM_REPO]&quot; -SelfUpdate &quot;[AIRC_SELF_UPDATE]&quot; -InstallTools &quot;[AIRC_INSTALL_TOOLS]&quot; -Profile &quot;[AIRC_PROFILE]&quot; -AgentLayer &quot;[AIRC_AGENT_LAYER]&quot; -CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;'
        }
    }
    $msiProps = switch ($Name) {
        'jeeves' {
            @"
    <Property Id="OPERFILE" Secure="yes" />
    <Property Id="OPERNAME" Secure="yes" />
    <Property Id="OPACCOUNTS" Secure="yes" />
    <Property Id="SKIPERGO" Secure="yes" />
    <Property Id="SKIPCOPY" Secure="yes" />
    <Property Id="BOBIVERSE_SKIP_TOOLS" Secure="yes" />
    <Property Id="BOBIVERSE_CRASH_REPORT" Secure="yes" />
    <!-- FR #4013 / #5150: fail closed before RemoveExistingProducts Error 1730 when not elevated. -->
    <Condition Message="jeeves install needs administrator rights">
      <![CDATA[Installed OR Privileged]]>
    </Condition>
"@
        }
        'bob' {
            @"
    <Property Id="MACHINEID" Secure="yes" />
    <Property Id="IRCHOST" Secure="yes" />
    <Property Id="SKIPCOPY" Secure="yes" />
    <Property Id="BOBIVERSE_SKIP_TOOLS" Secure="yes" />
    <Property Id="BOBIVERSE_CRASH_REPORT" Secure="yes" />
    <!-- FR #4013 / #5150: fail closed before RemoveExistingProducts Error 1730 when not elevated. -->
    <Condition Message="bob install needs administrator rights">
      <![CDATA[Installed OR Privileged]]>
    </Condition>
"@
        }
        'airc' {
            @"
    <Property Id="MACHINEID" Secure="yes" />
    <Property Id="AIRC_SHELL" Secure="yes" />
    <Property Id="AIRC_JOBS" Secure="yes" />
    <Property Id="AIRC_UPDATE" Secure="yes" />
    <Property Id="AIRC_EXTENSION" Secure="yes" />
    <Property Id="AIRC_REQUIRE_ACCOUNT" Secure="yes" />
    <Property Id="AIRC_ACCOUNTS" Secure="yes" />
    <Property Id="AIRC_SYNC_FROM_REPO" Secure="yes" />
    <Property Id="AIRC_SELF_UPDATE" Secure="yes" />
    <Property Id="AIRC_INSTALL_TOOLS" Secure="yes" />
    <Property Id="AIRC_PROFILE" Secure="yes" />
    <Property Id="AIRC_AGENT_LAYER" Secure="yes" />
    <Property Id="AIRC_PURGE" Secure="yes" />
    <Property Id="BOBIVERSE_CRASH_REPORT" Secure="yes" />
    <!-- FR #3684: Windows PowerShell >= 4.0 (Server 2012 R2 / walrus client baseline). -->
    <Property Id="POWERSHELLVERSION">
      <RegistrySearch Id="FindPowerShellVersion" Root="HKLM" Key="SOFTWARE\Microsoft\PowerShell\3\PowerShellEngine" Name="PowerShellVersion" Type="raw" Win64="yes" />
    </Property>
    <Condition Message="bobiverse airc requires Windows PowerShell 4.0 or newer (this machine: [POWERSHELLVERSION]).">
      <![CDATA[Installed OR (POWERSHELLVERSION >= "4.0")]]>
    </Condition>
    <!-- FR #4013: fail closed before RemoveExistingProducts Error 1730 when not elevated. -->
    <Condition Message="airc install needs administrator rights">
      <![CDATA[Installed OR Privileged]]>
    </Condition>
"@
        }
    }
    # FR #1566: airc MSI /x must stop/remove the Airc service before RemoveFiles.
    # Skip when UPGRADINGPRODUCTCODE is set (MajorUpgrade of this product) so AppParameters
    # stay readable for the new product's RunInstall / FR #1552 preserve path.
    # Return=ignore so a missing nssm/service never blocks ARP cleanup.
    # FR #4011: on MajorUpgrade, stop Airc BEFORE RemoveExistingProducts. Under
    # psexec -h -s (session 0), Restart Manager fails to shut down the service
    # (error 351) and Windows Installer itself crashes (msiexec 1601).
    # FR #4432: never schedule a deferred CA before RemoveExistingProducts after
    # InstallInitialize (Error 2613). airc uses MajorUpgrade afterInstallValidate so
    # REP runs before InstallInitialize; stop is immediate (QtExec64CmdLine) before
    # InstallValidate. Deferred StopAircBeforeUpgrade Before=REP is illegal and removed.
    $uninstallCaDecls = ''
    $uninstallCaSeq = ''
    if ($Name -eq 'airc') {
        # FR #4215: Defender exclusions BEFORE InstallFiles so Avast/Defender cannot block laying airc.exe.
        # Inline powershell (script not on disk yet). Return=ignore: AV CA must not fail the MSI.
        # Full Avast/AVG registry pass still runs from Install-Airc.ps1 after files land.
        # FR #7878: literal here-string. An expandable @" would eat $av / $_ / $n at pack time.
        $uninstallCaDecls = @'
    <!-- FR #4215: AV exclusions before InstallFiles (Defender path/process for airc.exe). -->
    <CustomAction Id="SetAvExcludeCmd" Property="RunAvExclude" Value="&quot;[System64Folder]WindowsPowerShell\v1.0\powershell.exe&quot; -NoProfile -ExecutionPolicy Bypass -Command &quot;try { Add-MpPreference -ExclusionPath '[INSTALLDIR]' -ErrorAction SilentlyContinue; Add-MpPreference -ExclusionPath '[INSTALLDIR]airc' -ErrorAction SilentlyContinue; Add-MpPreference -ExclusionProcess 'airc.exe' -ErrorAction SilentlyContinue } catch { }; try { $av = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop | Where-Object { $_.displayName -notmatch 'Defender' }); if ($av.Count -gt 0) { $n = ($av | ForEach-Object { $_.displayName }) -join ', '; Write-Warning ('FR #7878 third-party antivirus: ' + $n + '. Add an exception for [INSTALLDIR], [INSTALLDIR]airc, and airc.exe') } } catch { }; Write-Host 'FR4215 MSI AvExclude done'" Execute="immediate" />
    <CustomAction Id="RunAvExclude" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="no" Return="ignore" />
    <!-- FR #1566: quiet uninstall stops/removes Airc; ConsoleHome secrets stay (fleet). -->
    <!-- FR #3292: AIRC_PURGE=1 or workstation manifest purge_default removes secrets/homes. -->
    <CustomAction Id="SetUninstallCmd" Property="RunUninstall" Value="&quot;[INSTALLDIR]scripts\Uninstall-Airc.cmd&quot; -InstallRoot &quot;[INSTALLDIR].&quot; -Purge &quot;[AIRC_PURGE]&quot;" Execute="immediate" />
    <CustomAction Id="RunUninstall" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="no" Return="ignore" />
    <!-- FR #4011 / #4389 / #4432: immediate stop before InstallValidate (FilesInUse / RM 351). -->
    <!-- FR #4441: net.exe stop (waits) not sc.exe (async); matches airc-1.0.1-hotfix1.msi. -->
    <!-- Immediate CAQuietExec64 reads QtExec64CmdLine (not a property named after the CA). -->
    <CustomAction Id="SetStopAircValidateCmd" Property="QtExec64CmdLine" Value="&quot;[System64Folder]net.exe&quot; stop Airc" Execute="immediate" />
    <CustomAction Id="StopAircBeforeValidate" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="immediate" Return="ignore" />
'@
        $uninstallCaSeq = @"
      <Custom Action="SetAvExcludeCmd" Before="RunAvExclude">NOT REMOVE~="ALL"</Custom>
      <Custom Action="RunAvExclude" Before="InstallFiles">NOT REMOVE~="ALL"</Custom>
      <Custom Action="SetUninstallCmd" Before="RemoveFiles">REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE</Custom>
      <Custom Action="RunUninstall" After="SetUninstallCmd">REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE</Custom>
      <Custom Action="SetStopAircValidateCmd" Before="StopAircBeforeValidate">WIX_UPGRADE_DETECTED</Custom>
      <Custom Action="StopAircBeforeValidate" Before="InstallValidate">WIX_UPGRADE_DETECTED</Custom>
"@
    }
    # FR #2564: on RunInstall failure / MSI rollback, best-effort Start-Service so seats are not left dead.
    # Schedule RollbackRecover BEFORE RunInstall; Windows Installer runs Execute=rollback CAs when the deferred CA fails.
    $rollbackCaDecls = @"
    <!-- FR #2564: rollback restart ircBob/Airc/ircJeeves after failed RunInstall (1603 / CA fail). -->
    <CustomAction Id="SetRollbackRecoverCmd" Property="RollbackRecover" Value="&quot;[INSTALLDIR]scripts\Recover-BobiverseService.cmd&quot; -Product $Name -InstallRoot &quot;[INSTALLDIR].&quot; -Why msi-rollback" Execute="immediate" />
    <CustomAction Id="RollbackRecover" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="rollback" Impersonate="no" Return="ignore" />
"@
    # FR #3762: same-version msiexec /i is maintenance mode (Installed=1, REINSTALL unset) and
    # skipped RunInstall under "NOT Installed OR REINSTALL". Schedule whenever not full uninstall.
    $rollbackCaSeq = @"
      <Custom Action="SetRollbackRecoverCmd" After="SetInstallCmd">NOT REMOVE~="ALL"</Custom>
      <Custom Action="RollbackRecover" After="SetRollbackRecoverCmd">NOT REMOVE~="ALL"</Custom>
"@
    $guidMark = [guid]::NewGuid().ToString().ToUpper()
    # FR #3687: airc AgentLayerFeature Level=0 when client|workstation|AIRC_AGENT_LAYER=0
    # so msiexec never lays AGENTS/CLAUDE/GROK/.cursor/.grok/agent scripts even if RunInstall fails.
    if ($Name -eq 'airc') {
        $featureXml = @"
    <Feature Id="MainFeature" Title="bobiverse $Name" Level="1">
      <ComponentGroupRef Id="$cg" />
      <ComponentRef Id="CmpInstallDirMark" />
    </Feature>
    <Feature Id="AgentLayerFeature" Title="bobiverse airc agent layer" Level="1">
      <Condition Level="0"><![CDATA[AIRC_PROFILE ~= "client" OR AIRC_PROFILE ~= "workstation" OR AIRC_AGENT_LAYER = "0"]]></Condition>
      <ComponentGroupRef Id="BobiverseAircAgentLayerFiles" />
    </Feature>
"@
    } else {
        $featureXml = @"
    <Feature Id="MainFeature" Title="bobiverse $Name" Level="1">
      <ComponentGroupRef Id="$cg" />
      <ComponentRef Id="CmpInstallDirMark" />
    </Feature>
"@
    }
    # FR #4432: airc MajorUpgrade afterInstallValidate so RemoveExistingProducts runs
    # before InstallInitialize (avoids Error 2613 when any deferred CA would precede REP).
    $majorUpgradeSchedule = if ($Name -eq 'airc') { 'afterInstallValidate' } else { 'afterInstallInitialize' }
    $productWxs = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="bobiverse $Name" Language="1033" Version="$msiVersion"
      Manufacturer="SimonBarnett" UpgradeCode="$upgrade">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" InstallPrivileges="elevated" Platform="x64" />
    <MajorUpgrade DowngradeErrorMessage="A newer bobiverse $Name is installed." Schedule="$majorUpgradeSchedule" />
    <!-- FR #4011: PsExec -h -s (session 0) upgrades: Restart Manager error 351 crashes msiexec (1601). -->
    <Property Id="MSIRESTARTMANAGERCONTROL" Value="Disable" />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
$featureXml
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="INSTALLDIR" Name="$installDirName" />
    </Directory>
    <!-- t780u: <drive>:\ai discovered on the fixed disks (BOB_AI_ROOT / AIROOT= override); no hard-coded C:\ai. -->
    <Property Id="AIROOT" Secure="yes" />
$msiProps
    <Binary Id="FindAiRootJs" SourceFile="$findAiFile" />
    <CustomAction Id="FindAiRoot" BinaryKey="FindAiRootJs" JScriptCall="FindAiRoot" Execute="immediate" Return="check" />
    <CustomAction Id="SetInstallDirFromAiRoot" Property="INSTALLDIR" Value="[AIROOT]\$Name\" />
    <Component Id="CmpInstallDirMark" Directory="INSTALLDIR" Guid="$guidMark">
      <CreateFolder />
      <RegistryValue Root="HKLM" Key="Software\SimonBarnett\bobiverse\$Name" Name="InstallDir" Type="string" Value="[INSTALLDIR]" KeyPath="yes" />
    </Component>
    <!-- FR #3685: cmd /d /c call so .cmd exit codes reach CAQuietExec (bare .cmd CreateProcess can lose them). -->
    <!-- FR #3741: QuietExec requires the first token quoted; bare cmd.exe => 0x80070057 / msiexec 1603. -->
    <CustomAction Id="SetInstallCmd" Property="RunInstall" Value="&quot;[System64Folder]cmd.exe&quot; /d /c call &quot;[INSTALLDIR]scripts\$installCmd&quot;$installArgs" Execute="immediate" />
    <!-- #70: RunInstall forwards OPERFILE/SKIPERGO/MACHINEID/... via public Property Ids. -->
    <!-- Impersonate=yes so ObjectName resolves to the installing user (issue #3 LocalSystem). -->
    <!-- Return=check: nonzero Install-*.cmd must fail the MSI (1603) and roll back (FR #3685 / #2564). -->
    <CustomAction Id="RunInstall" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="yes" Return="check" />
$uninstallCaDecls
$rollbackCaDecls
    <InstallUISequence>
      <Custom Action="FindAiRoot" Before="CostInitialize">NOT AIROOT</Custom>
      <Custom Action="SetInstallDirFromAiRoot" Before="CostFinalize"></Custom>
    </InstallUISequence>
    <InstallExecuteSequence>
      <Custom Action="FindAiRoot" Before="CostInitialize">NOT AIROOT</Custom>
      <Custom Action="SetInstallDirFromAiRoot" Before="CostFinalize"></Custom>
      <!-- FR #3762: NOT REMOVE~="ALL" so same-version /i (maintenance) and repair re-run Install-*.cmd; uninstall still skips. -->
      <Custom Action="SetInstallCmd" After="InstallFiles">NOT REMOVE~="ALL"</Custom>
$rollbackCaSeq
      <Custom Action="RunInstall" After="RollbackRecover">NOT REMOVE~="ALL"</Custom>
$uninstallCaSeq
    </InstallExecuteSequence>
  </Product>
</Wix>
"@
    $pw = Join-Path $wixWork 'Product.wxs'
    [IO.File]::WriteAllText($pw, $productWxs, [Text.UTF8Encoding]::new($false))

    Push-Location $wixWork
    try {
        & $candle -nologo -ext $util "-dProductVersion=$msiVersion" "-dStageDir=$Stage" Product.wxs HarvestedFiles.wxs
        if ($LASTEXITCODE -ne 0) { throw "candle failed $LASTEXITCODE" }
        $msi = Join-Path $OutDir ("$Name-$Version.msi")
        if (Test-Path $msi) { Remove-Item -Force $msi }
        & $light -nologo -ext $util -cultures:en-us -out $msi Product.wixobj HarvestedFiles.wixobj
        if ($LASTEXITCODE -ne 0) { throw "light failed $LASTEXITCODE" }
        $hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLower()
        Set-Content -LiteralPath ($msi + '.sha256') -Value ("$hash  $Name-$Version.msi") -Encoding ascii
        Write-Host "INFO packed $msi sha256=$hash"
    } finally {
        Pop-Location
    }
    if (-not $KeepStage) {
        Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $wixWork -ErrorAction SilentlyContinue
    }
}

foreach ($p in $products) {
    $stage = Stage-Product $p
    Build-Msi $p $stage
}

Get-ChildItem $OutDir -Filter *.msi | Format-Table Name, Length -AutoSize
