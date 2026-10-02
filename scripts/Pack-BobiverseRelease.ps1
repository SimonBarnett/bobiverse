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
    [switch]$EmbedErgoPassword
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $Version = (Get-Content (Join-Path $RepoRoot 'src\VERSION') -Raw).Trim()
}
$msiVersion = $Version
if ($msiVersion -notmatch '^\d+\.\d+\.\d+') { throw "bad VERSION $Version" }

$fetchNssm = Join-Path $RepoRoot 'scripts\Fetch-Nssm.ps1'
$fetchWix = Join-Path $RepoRoot 'scripts\Fetch-Wix.ps1'
$fetchErgo = Join-Path $RepoRoot 'scripts\Fetch-Ergo.ps1'
$null = & $fetchNssm -OutDir (Join-Path $RepoRoot 'third_party\nssm\win64') -CacheDir (Join-Path $RepoRoot 'third_party\nssm')

$products = if ($Product -eq 'all') { @('jeeves', 'bob', 'airc') } else { @($Product) }

function Resolve-WatchAgentHealthSrc {
    foreach ($c in @(
            (Join-Path $RepoRoot 'third_party\Watch-AgentHealth'),
            $env:BOBIVERSE_WATCH_AGENTHEALTH,
            (Join-Path (Split-Path -Parent $RepoRoot) 'agentic_build\tools\Watch-AgentHealth'),
            (Join-Path $env:USERPROFILE 'agentic_build\tools\Watch-AgentHealth'),
            'C:\Users\Administrator\agentic_build\tools\Watch-AgentHealth'
        )) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'Watch-AgentHealth.ps1'))) {
            return $c
        }
    }
    return $null
}

function Stage-Product([string]$Name) {
    $stage = Join-Path $OutDir ("$Name-$Version")
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force -Path "$stage\scripts", "$stage\docs", "$stage\.grok\skills", "$stage\src", "$stage\config", "$stage\third_party\nssm\win64" | Out-Null
    Copy-Item (Join-Path $RepoRoot 'scripts\*') (Join-Path $stage 'scripts') -Recurse -Force
    # Issue #2: do not ship __pycache__ (self-copy / heat noise)
    Get-ChildItem -Path (Join-Path $stage 'scripts') -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $RepoRoot 'src\VERSION') (Join-Path $stage 'VERSION') -Force
    Copy-Item (Join-Path $RepoRoot 'src\VERSION') (Join-Path $stage 'src\VERSION') -Force

    # Product AGENTS.md (repo AGENTS.<product>.md -> stage AGENTS.md)
    $agentsSrc = Join-Path $RepoRoot ("AGENTS.$Name.md")
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
    $docsSrc = Join-Path $RepoRoot 'docs'
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
        $from = Join-Path $docsSrc $d
        if (Test-Path -LiteralPath $from) {
            Copy-Item -LiteralPath $from -Destination (Join-Path $docsDest $d) -Force
        }
    }
    $productDocsDir = Join-Path $docsSrc $Name
    if (Test-Path -LiteralPath $productDocsDir) {
        Copy-Item -Path (Join-Path $productDocsDir '*') -Destination $docsDest -Recurse -Force
        Write-Host "INFO $Name staged docs/$Name/ into docs\"
    }
    Write-Host ("INFO $Name staged docs: {0}" -f (($docsToCopy | Sort-Object) -join ', '))

    # Skills: product skill + harvest only (do not ship sibling product skills)
    $skillsRoot = Join-Path $RepoRoot '.grok\skills'
    $skillsDest = Join-Path $stage '.grok\skills'
    # This product's whole skill book: bobiverse-<p> + bobiverse-<p>-commands / -troubleshooting / ... + the shared fleet-ops book.
    $productSkill = "bobiverse-$Name"
    $bookDirs = @(Get-ChildItem -LiteralPath $skillsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $productSkill -or $_.Name -like "$productSkill-*" -or $_.Name -eq 'bobiverse-fleet-ops' })
    if (-not ($bookDirs | Where-Object { $_.Name -eq $productSkill })) {
        Write-Host "WARN $Name missing .grok/skills/$productSkill"
    }
    foreach ($bd in $bookDirs) {
        New-Item -ItemType Directory -Force -Path (Join-Path $skillsDest $bd.Name) | Out-Null
        Copy-Item -Path (Join-Path $bd.FullName '*') -Destination (Join-Path $skillsDest $bd.Name) -Recurse -Force
    }
    Write-Host ("INFO $Name staged skill books: {0}" -f (($bookDirs | ForEach-Object Name) -join ', '))
    $harvestSrc = Join-Path $skillsRoot 'harvest'
    $harvestAliasSrc = Join-Path $skillsRoot 'harvest-agent-skills'
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
    $trayIcoSrc = Join-Path $RepoRoot 'third_party\bob-tray\assets\bob-systray.ico'
    if (Test-Path -LiteralPath $trayIcoSrc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'assets') | Out-Null
        Copy-Item -LiteralPath $trayIcoSrc -Destination (Join-Path $stage 'assets\bob-systray.ico') -Force
    } else {
        Write-Host 'WARN third_party/bob-tray/assets/bob-systray.ico missing - Start Menu shortcuts fall back to default icons'
    }

    Copy-Item (Join-Path $RepoRoot 'third_party\nssm\win64\nssm.exe') (Join-Path $stage 'third_party\nssm\win64\nssm.exe') -Force
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
        $null = & $fetchErgo -OutDir $ergoStage -CacheDir (Join-Path $RepoRoot 'third_party\ergo')
        if (-not (Test-Path -LiteralPath (Join-Path $ergoStage 'ergo.exe'))) {
            throw 'jeeves pack requires ergo.exe (Fetch-Ergo failed)'
        }
        # Optional operator ircd.yaml (never from git secrets); else Install seeds default.yaml
        foreach ($c in @(
                (Join-Path $RepoRoot 'config\ircd.yaml'),
                $env:BOBIVERSE_IRCD_YAML,
                'C:\ai\ergo\ircd.yaml'
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
            $from = Join-Path $RepoRoot "tools\$tf"
            if (-not (Test-Path -LiteralPath $from)) { throw "jeeves pack requires tools\$tf (webhooks, #53)" }
            Copy-Item -LiteralPath $from -Destination (Join-Path $toolsStage $tf) -Force
        }
        Write-Host "INFO jeeves staged tools\bob_git_hook.py + New-BobGitWebhook.ps1"
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
            Write-Host "INFO bob staged Watch-AgentHealth from $wahSrc"
        } else {
            Write-Host 'WARN bob pack: Watch-AgentHealth source missing (Desktop install will skip)'
        }

        # TipForm companion tray (vendored from agentic_build) -> InstallRoot tools/src/assets
        $traySrc = Join-Path $RepoRoot 'third_party\bob-tray'
        $syncTray = Join-Path $RepoRoot 'scripts\Sync-BobTrayFromAgenticBuild.ps1'
        if (-not (Test-Path -LiteralPath (Join-Path $traySrc 'tools\Watch-BobTray.ps1'))) {
            if (Test-Path -LiteralPath $syncTray) {
                Write-Host 'INFO bob tray missing; running Sync-BobTrayFromAgenticBuild.ps1'
                & $syncTray -RepoRoot $RepoRoot | Out-Null
            }
        }
        if (-not (Test-Path -LiteralPath (Join-Path $traySrc 'tools\Watch-BobTray.ps1'))) {
            throw 'bob pack requires third_party/bob-tray/tools/Watch-BobTray.ps1 (run Sync-BobTrayFromAgenticBuild.ps1)'
        }
        foreach ($sub in @('tools', 'assets')) {
            $from = Join-Path $traySrc $sub
            $to = Join-Path $stage $sub
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
        }
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
        Write-Host ("INFO bob staged TipForm tray from {0} pin={1}" -f $traySrc, ((Get-Content (Join-Path $traySrc 'PIN.txt') -TotalCount 1).Trim()))
    }
    return $stage
}

function Build-Msi([string]$Name, [string]$Stage) {
    if ($SkipMsi) {
        Write-Host "INFO SkipMsi stage=$Stage"
        return
    }
    $wixBin = & $fetchWix -CacheDir (Join-Path $RepoRoot 'third_party\wix')
    $candle = Join-Path $wixBin 'candle.exe'
    $light = Join-Path $wixBin 'light.exe'
    $heat = Join-Path $wixBin 'heat.exe'
    $util = Join-Path $wixBin 'WixUtilExtension.dll'
    $wixWork = Join-Path $OutDir ("wix-$Name-$Version")
    if (Test-Path $wixWork) { Remove-Item -Recurse -Force $wixWork }
    New-Item -ItemType Directory -Force -Path $wixWork | Out-Null

    $installDirName = $Name
    $installPath = "C:\ai\$Name"
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
    # #70 (v0.1.20): the same for ergo\ergo.exe. C:\ai\ergo\ergo.exe was found HARD-LINKED to the pack's
    # C:\ai\jeeves\ergo\ergo.exe, so the MSI rewriting its own copy rewrote the running Ergo binary and Windows
    # Restart Manager bounced BobIrcd (pid change, every client reconnected). The pack keeps shipping ergo.exe (fresh
    # installs seed C:\ai\ergo from it) but an upgrade must never remove/rewrite an existing one: Ergo upgrades are
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
    <SetDirectory Id="INSTALLDIR" Value="$installPath" />
    <Component Id="CmpInstallDirMark" Directory="INSTALLDIR" Guid="$guidMark">
      <CreateFolder />
      <RegistryValue Root="HKLM" Key="Software\SimonBarnett\bobiverse\$Name" Name="InstallDir" Type="string" Value="[INSTALLDIR]" KeyPath="yes" />
    </Component>
    <CustomAction Id="SetInstallCmd" Property="RunInstall" Value="&quot;[INSTALLDIR]scripts\$installCmd&quot;" Execute="immediate" />
    <!-- Impersonate=yes so ObjectName resolves to the installing user (issue #3 LocalSystem). -->
    <CustomAction Id="RunInstall" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="yes" Return="check" />
    <InstallExecuteSequence>
      <Custom Action="SetInstallCmd" After="InstallFiles">NOT Installed OR REINSTALL</Custom>
      <Custom Action="RunInstall" After="SetInstallCmd">NOT Installed OR REINSTALL</Custom>
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
