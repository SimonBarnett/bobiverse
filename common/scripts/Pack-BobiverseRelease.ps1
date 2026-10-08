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
    # Issue #4: public GitHub Release MSIs must NOT embed the live Ergo PASS.
    # Pass -EmbedErgoPassword only for private/offline packs.
    [switch]$EmbedErgoPassword,
    # Tests only (needs -SkipMsi): stage the worker/plan folders without compiling bob-worker.exe (PyInstaller, ~40 s).
    [switch]$SkipWorkerExe,
    # Tests only (needs -SkipMsi): skip bob-ear.exe (FR #1481 PyInstaller, ~40 s).
    [switch]$SkipEarExe,
    # Tests only (needs -SkipMsi): skip jeeves.exe (FR #2301 / WP3 PyInstaller).
    [switch]$SkipJeevesExe,
    # Tests only (needs -SkipMsi): skip airc.exe (FR #2397 PyInstaller).
    [switch]$SkipAircExe
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Bobiverse-Common.ps1')
# t773u: the repo is split per service (common\ jeeves\ bob\ airc\); this script lives in common\scripts. The STAGE stays flat.
if (-not $RepoRoot) {
    $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $Version = (Get-Content (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION') -Raw).Trim()
}
$msiVersion = $Version
if ($msiVersion -notmatch '^\d+\.\d+\.\d+') { throw "bad VERSION $Version" }

$fetchNssm = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Nssm.ps1')
$fetchWix = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Wix.ps1')
$fetchErgo = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Fetch-Ergo.ps1')
$null = & $fetchNssm -OutDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm\win64') -CacheDir (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm')

if ($SkipWorkerExe -and -not $SkipMsi) { throw '-SkipWorkerExe is only allowed together with -SkipMsi (an MSI without bob-worker.exe must never ship)' }
if ($SkipEarExe -and -not $SkipMsi) { throw '-SkipEarExe is only allowed together with -SkipMsi (an MSI without bob-ear.exe must never ship; FR #1481)' }
if ($SkipJeevesExe -and -not $SkipMsi) { throw '-SkipJeevesExe is only allowed together with -SkipMsi (an MSI without jeeves.exe must never ship; FR #2301)' }
if ($SkipAircExe -and -not $SkipMsi) { throw '-SkipAircExe is only allowed together with -SkipMsi (an MSI without airc.exe must never ship; FR #2397)' }

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
    # t762u: bob MSI payload gains worker\ (bob-worker.exe + AGENTS/skills) and plan\ (plan-mode skills); built by the shared Common function.
    # FR #1481: also stage scripts\bob-ear.exe (frozen irc_agent) so ircBob does not need system Python for the ear.
    $made = Sync-BobiverseAgentFolders -RepoRoot $RepoRoot -Destination $Stage
    if ($made -lt 2) { throw 'bob pack requires bob-agents\worker and bob-agents\plan' }
    if ($SkipWorkerExe) {
        Write-Host 'WARN bob pack: -SkipWorkerExe (test stage; no bob-worker.exe)'
    } else {
        $buildWorker = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-BobWorker.ps1')
        $exe = (& $buildWorker -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
        if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { throw 'Build-BobWorker.ps1 did not produce bob-worker.exe' }
        Copy-Item -LiteralPath $exe -Destination (Join-Path $Stage 'worker\bob-worker.exe') -Force
        Write-Host 'INFO bob staged worker\bob-worker.exe'
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

function Stage-Product([string]$Name) {
    $stage = Join-Path $OutDir ("$Name-$Version")
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force -Path "$stage\scripts", "$stage\docs", "$stage\.grok\skills", "$stage\src", "$stage\config", "$stage\third_party\nssm\win64" | Out-Null
    # t773u: the flat staged scripts\ is the UNION of common\scripts + jeeves\scripts + bob\scripts + airc\scripts.
    Copy-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts' -Dest (Join-Path $stage 'scripts')
    # Issue #2: do not ship __pycache__ (self-copy / heat noise)
    Get-ChildItem -Path (Join-Path $stage 'scripts') -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION') (Join-Path $stage 'VERSION') -Force
    Copy-Item (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'src\VERSION') (Join-Path $stage 'src\VERSION') -Force
    # t797u: BUILD.json = what the tray About dialog shows as version / build date / commit for this install folder.
    $buildCommit = ''
    try { $buildCommit = [string](& git -C $RepoRoot rev-parse --short HEAD 2>$null | Select-Object -First 1) } catch { }
    ([ordered]@{ product = $Name; version = $Version; built_utc = [datetime]::UtcNow.ToString('o'); commit = $buildCommit.Trim() } |
        ConvertTo-Json -Compress) | Set-Content -LiteralPath (Join-Path $stage 'BUILD.json') -Encoding ascii

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

    # Skills: product skill + harvest only (do not ship sibling product skills)
    $skillsDirs = @(Get-BobiverseRepoDirs -Root $RepoRoot -Sub '.grok\skills')
    function Find-RepoSkill([string]$n) { foreach ($sd in $skillsDirs) { $c = Join-Path $sd $n; if (Test-Path -LiteralPath $c) { return $c } } return (Join-Path $skillsDirs[0] $n) }
    $skillsDest = Join-Path $stage '.grok\skills'
    # This product's whole skill book: bobiverse-<p> + bobiverse-<p>-commands / -troubleshooting / ... + the shared fleet-ops book.
    $productSkill = "bobiverse-$Name"
    # FR #954: jeeves also stages monitor-start (first-turn auto-start skill).
    $bookDirs = @($skillsDirs | ForEach-Object { Get-ChildItem -LiteralPath $_ -Directory -ErrorAction SilentlyContinue } |
            Where-Object {
                $_.Name -eq $productSkill -or $_.Name -like "$productSkill-*" -or $_.Name -eq 'bobiverse-fleet-ops' -or
                ($Name -eq 'jeeves' -and $_.Name -eq 'monitor-start')
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

    # Bobiverse systray icon: every product's Start Menu shortcuts use it (bob also gets it via the tray payload).
    $trayIcoSrc = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets\bob-systray.ico')
    if (Test-Path -LiteralPath $trayIcoSrc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'assets') | Out-Null
        Copy-Item -LiteralPath $trayIcoSrc -Destination (Join-Path $stage 'assets\bob-systray.ico') -Force
    } else {
        Write-Host 'WARN third_party/bob-tray/assets/bob-systray.ico missing - Start Menu shortcuts fall back to default icons'
    }

    Copy-Item (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\nssm\win64\nssm.exe') (Join-Path $stage 'third_party\nssm\win64\nssm.exe') -Force
    # Issue #4: do not embed live Ergo PASS into public release assets by default.
    $stageErgo = Join-Path $stage 'config\ergo.password'
    if ($EmbedErgoPassword) {
        foreach ($c in @(
                (Join-Path $RepoRoot 'config\ergo.password'),
                (Join-Path $env:USERPROFILE '.grok\ergo\connect.password')
            )) {
            if (Test-Path -LiteralPath $c) {
                Copy-Item $c $stageErgo -Force
                Write-Host "INFO $Name embedded config/ergo.password from $c (-EmbedErgoPassword)"
                break
            }
        }
        if (-not (Test-Path -LiteralPath $stageErgo)) {
            throw "-EmbedErgoPassword set but no config/ergo.password or ~/.grok/ergo/connect.password found"
        }
    } else {
        if (Test-Path -LiteralPath $stageErgo) {
            Remove-Item -LiteralPath $stageErgo -Force
            Write-Host "WARN $Name removed staged config/ergo.password (issue #4 public pack guard)"
        }
        Write-Host "INFO $Name skipping Ergo PASS embed (issue #4; pass -EmbedErgoPassword for private packs)"
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
            $buildWatcher = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-BobWatcher.ps1')
            $watcherExe = (& $buildWatcher -RepoRoot $RepoRoot -OutDir $OutDir | Select-Object -Last 1)
            if (-not $watcherExe -or -not (Test-Path -LiteralPath $watcherExe)) { throw 'Build-BobWatcher.ps1 did not produce Watch-AgentHealth.exe' }
            Copy-Item -LiteralPath $watcherExe -Destination (Join-Path $wahDest 'Watch-AgentHealth.exe') -Force
            Write-Host 'INFO bob staged Watch-AgentHealth.exe'
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
            $buildDialogs = (Get-BobiverseRepoPath -Root $RepoRoot -Rel 'scripts\Build-BobDialogs.ps1')
            $dlgExes = @(& $buildDialogs -RepoRoot $RepoRoot -OutDir (Join-Path $stage 'tools'))
            if ($dlgExes.Count -lt 3) { throw 'Build-BobDialogs.ps1 did not produce bob-about.exe + bob-status.exe + bob-tray.exe' }
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
        Stage-BobAgentFolders -Stage $stage
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
    }
    return $stage
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
    & $heat dir $Stage -cg $cg -gg -sfrag -srd -sreg -scom -dr INSTALLDIR -var var.StageDir -out $harvested
    if ($LASTEXITCODE -ne 0) { throw "heat failed $LASTEXITCODE" }

    # #70 (v0.1.19): the pack's nssm.exe is the service binary of running Windows services (ircJeeves/ircBob, and on
    # older boxes also BobIrcd/Ergo). heat gives every build fresh component GUIDs, so a MajorUpgrade used to REMOVE
    # and re-lay nssm.exe -> the services holding it were stopped (Ergo bounced, all clients reconnected).
    # Permanent = the old product never removes it; NeverOverwrite = the new product never rewrites an existing copy.
    # The file is byte-identical across releases (nssm 2.24), so keeping the installed one is always correct.
    [xml]$hx = Get-Content -LiteralPath $harvested -Raw -Encoding UTF8
    $wns = New-Object System.Xml.XmlNamespaceManager($hx.NameTable)
    $wns.AddNamespace('w', 'http://schemas.microsoft.com/wix/2006/wi')
    $nssmFiles = @($hx.SelectNodes('//w:File', $wns) | Where-Object { ([string]$_.GetAttribute('Source')) -match '[\\/]nssm\.exe$' })
    if ($nssmFiles.Count -lt 1) { throw 'nssm.exe component not found in harvested files (cannot mark it permanent)' }
    foreach ($nf in $nssmFiles) {
        $nc = $nf.ParentNode
        $nc.SetAttribute('Permanent', 'yes')
        $nc.SetAttribute('NeverOverwrite', 'yes')
        # Stable component GUID (per product) so every release refers to the SAME component, not a fresh one.
        $nc.SetAttribute('Guid', '{' + ([guid]::new([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes("bobiverse-$Name-nssm-component"))).ToString().ToUpper()) + '}')
    }
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
    $hx.Save($harvested)
    Write-Host ("INFO marked {0} nssm.exe component(s) Permanent+NeverOverwrite" -f $nssmFiles.Count)

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
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -OperFile &quot;[OPERFILE]&quot; -OperName &quot;[OPERNAME]&quot; -OpAccounts &quot;[OPACCOUNTS]&quot; -MsiSkipErgo &quot;[SKIPERGO]&quot; -MsiSkipCopy &quot;[SKIPCOPY]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot;'
        }
        'bob' {
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -MachineId &quot;[MACHINEID]&quot; -IrcHost &quot;[IRCHOST]&quot; -MsiSkipCopy &quot;[SKIPCOPY]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot;'
        }
        'airc' {
            # FR #3287: capability + account MSI props (empty = installer defaults / prior identity).
            # FR #3289: AIRC_SYNC_FROM_REPO / AIRC_SELF_UPDATE (empty = fresh sync off / self_update on, or keep prior).
            # FR #3290: AIRC_INSTALL_TOOLS=1 opts into git/gh/python/node bootstrap (default skip when airc.exe present).
            ' -InstallRoot &quot;[INSTALLDIR].&quot; -MachineId &quot;[MACHINEID]&quot; -MsiProductVersion &quot;[ProductVersion]&quot; -ShellMode &quot;[AIRC_SHELL]&quot; -Jobs &quot;[AIRC_JOBS]&quot; -UpdateCap &quot;[AIRC_UPDATE]&quot; -RequireAccount &quot;[AIRC_REQUIRE_ACCOUNT]&quot; -Accounts &quot;[AIRC_ACCOUNTS]&quot; -SyncFromRepo &quot;[AIRC_SYNC_FROM_REPO]&quot; -SelfUpdate &quot;[AIRC_SELF_UPDATE]&quot; -InstallTools &quot;[AIRC_INSTALL_TOOLS]&quot;'
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
"@
        }
        'bob' {
            @"
    <Property Id="MACHINEID" Secure="yes" />
    <Property Id="IRCHOST" Secure="yes" />
    <Property Id="SKIPCOPY" Secure="yes" />
    <Property Id="BOBIVERSE_SKIP_TOOLS" Secure="yes" />
"@
        }
        'airc' {
            @"
    <Property Id="MACHINEID" Secure="yes" />
    <Property Id="AIRC_SHELL" Secure="yes" />
    <Property Id="AIRC_JOBS" Secure="yes" />
    <Property Id="AIRC_UPDATE" Secure="yes" />
    <Property Id="AIRC_REQUIRE_ACCOUNT" Secure="yes" />
    <Property Id="AIRC_ACCOUNTS" Secure="yes" />
    <Property Id="AIRC_SYNC_FROM_REPO" Secure="yes" />
    <Property Id="AIRC_SELF_UPDATE" Secure="yes" />
    <Property Id="AIRC_INSTALL_TOOLS" Secure="yes" />
"@
        }
    }
    # FR #1566: airc MSI /x must stop/remove the Airc service before RemoveFiles.
    # Skip when UPGRADINGPRODUCTCODE is set (MajorUpgrade of this product) so AppParameters
    # stay readable for the new product's RunInstall / FR #1552 preserve path.
    # Return=ignore so a missing nssm/service never blocks ARP cleanup.
    $uninstallCaDecls = ''
    $uninstallCaSeq = ''
    if ($Name -eq 'airc') {
        $uninstallCaDecls = @"
    <!-- FR #1566: quiet uninstall stops/removes Airc; ConsoleHome secrets stay. -->
    <CustomAction Id="SetUninstallCmd" Property="RunUninstall" Value="&quot;[INSTALLDIR]scripts\Uninstall-Airc.cmd&quot; -InstallRoot &quot;[INSTALLDIR].&quot;" Execute="immediate" />
    <CustomAction Id="RunUninstall" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="no" Return="ignore" />
"@
        $uninstallCaSeq = @"
      <Custom Action="SetUninstallCmd" Before="RemoveFiles">REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE</Custom>
      <Custom Action="RunUninstall" After="SetUninstallCmd">REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE</Custom>
"@
    }
    # FR #2564: on RunInstall failure / MSI rollback, best-effort Start-Service so seats are not left dead.
    # Schedule RollbackRecover BEFORE RunInstall; Windows Installer runs Execute=rollback CAs when the deferred CA fails.
    $rollbackCaDecls = @"
    <!-- FR #2564: rollback restart ircBob/Airc/ircJeeves after failed RunInstall (1603 / CA fail). -->
    <CustomAction Id="SetRollbackRecoverCmd" Property="RollbackRecover" Value="&quot;[INSTALLDIR]scripts\Recover-BobiverseService.cmd&quot; -Product $Name -InstallRoot &quot;[INSTALLDIR].&quot; -Why msi-rollback" Execute="immediate" />
    <CustomAction Id="RollbackRecover" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="rollback" Impersonate="no" Return="ignore" />
"@
    $rollbackCaSeq = @"
      <Custom Action="SetRollbackRecoverCmd" After="SetInstallCmd">NOT Installed OR REINSTALL</Custom>
      <Custom Action="RollbackRecover" After="SetRollbackRecoverCmd">NOT Installed OR REINSTALL</Custom>
"@
    $guidMark = [guid]::NewGuid().ToString().ToUpper()
    $productWxs = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="bobiverse $Name" Language="1033" Version="$msiVersion"
      Manufacturer="SimonBarnett" UpgradeCode="$upgrade">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" Platform="x64" />
    <MajorUpgrade DowngradeErrorMessage="A newer bobiverse $Name is installed." Schedule="afterInstallInitialize" />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
    <Feature Id="MainFeature" Title="bobiverse $Name" Level="1">
      <ComponentGroupRef Id="$cg" />
      <ComponentRef Id="CmpInstallDirMark" />
    </Feature>
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
    <CustomAction Id="SetInstallCmd" Property="RunInstall" Value="&quot;[INSTALLDIR]scripts\$installCmd&quot;$installArgs" Execute="immediate" />
    <!-- #70: RunInstall forwards OPERFILE/SKIPERGO/MACHINEID/... via public Property Ids. -->
    <!-- Impersonate=yes so ObjectName resolves to the installing user (issue #3 LocalSystem). -->
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
      <Custom Action="SetInstallCmd" After="InstallFiles">NOT Installed OR REINSTALL</Custom>
$rollbackCaSeq
      <Custom Action="RunInstall" After="RollbackRecover">NOT Installed OR REINSTALL</Custom>
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
