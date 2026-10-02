#Requires -Version 5.1
<#
.SYNOPSIS
  Vendor TipForm Watch-BobTray + BobBridge into third_party/bob-tray for bob MSI.
.NOTES
  Copies allowlisted files from a local agentic_build tree. Writes PIN.txt = git SHA.
  Does NOT ship Update-BobSystrayFromGit git-pull; MSI updates use Check-BobiverseUpdate.
  ASCII-only for Windows PowerShell 5.1.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$AgenticBuildRoot = '',
    [string]$OutDir = '',
    [string]$PinSha = ''
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'third_party\bob-tray' }

function Resolve-AgenticBuildRoot {
    param([string]$Preferred)
    foreach ($c in @(
            $Preferred,
            $env:AGENTIC_BUILD_ROOT,
            (Join-Path (Split-Path -Parent $RepoRoot) 'agentic_build'),
            'C:\ai\agentic_build',
            (Join-Path $env:USERPROFILE 'agentic_build'),
            'C:\Users\Administrator\agentic_build'
        )) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'tools\Watch-BobTray.ps1'))) {
            return [IO.Path]::GetFullPath($c)
        }
    }
    return $null
}

$srcRoot = Resolve-AgenticBuildRoot -Preferred $AgenticBuildRoot
if (-not $srcRoot) {
    throw 'agentic_build with tools\Watch-BobTray.ps1 not found (set -AgenticBuildRoot or AGENTIC_BUILD_ROOT)'
}

if (-not $PinSha) {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $PinSha = (& git -C $srcRoot rev-parse HEAD 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) { $PinSha = '' }
    }
}
if (-not $PinSha) { $PinSha = 'unknown' }
$PinSha = ([string]$PinSha).Trim()

$toolFiles = @(
    'Watch-BobTray.ps1',
    'Start-BobFleetTray.ps1',
    'Bootstrap-BobSystray.ps1',
    'Install-VisionarySkills.ps1',
    'Show-BobSystrayUpdatingDialog.ps1',
    'Stop-BobSystrayPriorAgents.ps1',
    'Get-BobBoxUsage.ps1'
)
# Optional tidy helpers referenced by Start-BobFleetTray (warn-only if missing upstream)
$optionalTools = @(
    'Cleanup-OrphanAgents.ps1',
    'Clear-BobOrphanNotifyIcons.ps1',
    'Bob-WatchSeatSlot.ps1'
)

# #60: bobiverse-owned tools that upstream does not ship (or ships a machine-specific copy of).
# They are preserved across a re-sync so the vendored tray keeps working on every machine.
$ownedTools = @('Get-CursorAgentUsage.py')
$ownedKeep = @{}
foreach ($leaf in $ownedTools) {
    $p = Join-Path $OutDir "tools\$leaf"
    if (Test-Path -LiteralPath $p) { $ownedKeep[$leaf] = [IO.File]::ReadAllBytes($p) }
}
if (Test-Path -LiteralPath $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path @(
    (Join-Path $OutDir 'tools'),
    (Join-Path $OutDir 'src'),
    (Join-Path $OutDir 'assets'),
    (Join-Path $OutDir 'config')
) | Out-Null

foreach ($leaf in $toolFiles) {
    $from = Join-Path $srcRoot "tools\$leaf"
    if (-not (Test-Path -LiteralPath $from)) {
        throw "required tray file missing: $from"
    }
    Copy-Item -LiteralPath $from -Destination (Join-Path $OutDir "tools\$leaf") -Force
}
foreach ($leaf in $ownedKeep.Keys) {
    [IO.File]::WriteAllBytes((Join-Path $OutDir "tools\$leaf"), $ownedKeep[$leaf])
}
foreach ($leaf in $optionalTools) {
    if ($ownedKeep.ContainsKey($leaf)) { continue }
    $from = Join-Path $srcRoot "tools\$leaf"
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $OutDir "tools\$leaf") -Force
    }
}

# Whole BobBridge module tree (Public + Private); skip backup junk
$modSrc = Join-Path $srcRoot 'src'
foreach ($leaf in @('BobBridge.psd1', 'BobBridge.psm1')) {
    $from = Join-Path $modSrc $leaf
    if (-not (Test-Path -LiteralPath $from)) { throw "missing $from" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $OutDir "src\$leaf") -Force
}
foreach ($sub in @('Public', 'Private')) {
    $fromDir = Join-Path $modSrc $sub
    $toDir = Join-Path $OutDir "src\$sub"
    if (-not (Test-Path -LiteralPath $fromDir)) { throw "missing $fromDir" }
    New-Item -ItemType Directory -Force -Path $toDir | Out-Null
    Get-ChildItem -LiteralPath $fromDir -File | Where-Object {
        $_.Name -notmatch '\.bak($|-)' -and $_.Extension -in @('.ps1', '.psm1', '.psd1')
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $toDir $_.Name) -Force
    }
}

$ico = Join-Path $srcRoot 'assets\bob-systray.ico'
if (-not (Test-Path -LiteralPath $ico)) { throw "missing $ico" }
Copy-Item -LiteralPath $ico -Destination (Join-Path $OutDir 'assets\bob-systray.ico') -Force

foreach ($cfg in @('bobiverse.json', 'bob-seats.json', 'default.json', 'fleet-registry.json')) {
    $from = Join-Path $srcRoot "config\$cfg"
    if (Test-Path -LiteralPath $from) {
        # Never copy secret material; these JSON files are public fleet registry/config only
        Copy-Item -LiteralPath $from -Destination (Join-Path $OutDir "config\$cfg") -Force
    }
}

# MSI companion: no agentic_build git-pull. Restart uses Check-BobiverseUpdate when present.
$msiUpdate = @'
#Requires -Version 5.1
# Vendored for bob MSI TipForm tray. Does NOT git-pull agentic_build.
# Product updates: scripts\Check-BobiverseUpdate.ps1 (GitHub Releases MSI).
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$Branch = 'main',
    [switch]$Force,
    [switch]$WhatIf,
    [switch]$SkipDialog,
    [string]$GitExe = 'git'
)

$ErrorActionPreference = 'Continue'
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)

$result = [ordered]@{
    ok      = $true
    updated = $false
    behind  = $false
    count   = 0
    dialog  = $false
    error   = $null
    summary = 'msi-tray: skip agentic_build git-pull (use Check-BobiverseUpdate)'
}

$checker = Join-Path $RepoRoot 'scripts\Check-BobiverseUpdate.ps1'
if (-not (Test-Path -LiteralPath $checker)) {
    $checker = Join-Path (Split-Path $RepoRoot -Parent) 'bob\scripts\Check-BobiverseUpdate.ps1'
}
if ($Force -and (Test-Path -LiteralPath $checker) -and -not $WhatIf) {
    try {
        $ps = (Get-Command powershell.exe).Source
        & $ps -NoProfile -ExecutionPolicy Bypass -File $checker -Product bob -InstallRoot $RepoRoot -DryRun 2>&1 | Out-Null
        $result.summary = 'msi-tray: Check-BobiverseUpdate -DryRun invoked'
    } catch {
        $result.error = $_.Exception.Message
        $result.summary = 'msi-tray: Check-BobiverseUpdate dry-run failed (non-fatal)'
    }
}

$result | ConvertTo-Json -Compress
exit 0
'@
[IO.File]::WriteAllText(
    (Join-Path $OutDir 'tools\Update-BobSystrayFromGit.ps1'),
    $msiUpdate.TrimStart() + "`r`n",
    [Text.UTF8Encoding]::new($false)
)

[IO.File]::WriteAllText(
    (Join-Path $OutDir 'PIN.txt'),
    ($PinSha + "`r`n"),
    [Text.UTF8Encoding]::new($false)
)

$watch = Join-Path $OutDir 'tools\Watch-BobTray.ps1'
if (-not (Test-Path -LiteralPath $watch)) {
    throw "sync failed: missing $watch"
}

Write-Host "INFO synced bob-tray from $srcRoot pin=$PinSha -> $OutDir"
Get-ChildItem $OutDir -Recurse -File | Measure-Object | ForEach-Object {
    Write-Host ("INFO files={0}" -f $_.Count)
}
return $OutDir
