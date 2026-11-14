#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7248: stage a CI tray hotpatch tree (exes + display scripts) with per-file SHA-256.
.DESCRIPTION
  Layout matches a live bob install: tools\ (exes + Watch-BobTray.ps1 …), src\ (BobBridge),
  assets\. Does not copy tray\config (live bobiverse.json / seats stay on the box).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$StageDir,
    [string]$ExeDir = '',
    [string]$Commit = ''
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath($RepoRoot.TrimEnd('\', '/'))
$stage = [IO.Path]::GetFullPath($StageDir.TrimEnd('\', '/'))
New-Item -ItemType Directory -Force -Path $stage | Out-Null

function Copy-BobTrayTree {
    param([string]$From, [string]$To, [string[]]$ExcludeName = @())
    if (-not (Test-Path -LiteralPath $From)) { return }
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    Get-ChildItem -LiteralPath $From -Recurse -File | ForEach-Object {
        if ($ExcludeName -contains $_.Name) { return }
        $rel = $_.FullName.Substring($From.Length).TrimStart('\', '/')
        $dest = Join-Path $To $rel
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
    }
}

$tray = Join-Path $repo 'bob\tray'
if (-not (Test-Path -LiteralPath $tray)) { $tray = Join-Path $repo 'tray' }
Copy-BobTrayTree -From (Join-Path $tray 'src') -To (Join-Path $stage 'src')
Copy-BobTrayTree -From (Join-Path $tray 'tools') -To (Join-Path $stage 'tools')
Copy-BobTrayTree -From (Join-Path $tray 'assets') -To (Join-Path $stage 'assets')

if ($ExeDir -and (Test-Path -LiteralPath $ExeDir)) {
    $exeRoot = [IO.Path]::GetFullPath($ExeDir)
    $tools = Join-Path $stage 'tools'
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    foreach ($name in @('bob-tray.exe', 'bob-status.exe', 'bob-about.exe')) {
        $src = Join-Path $exeRoot $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $stage $name) -Force
            Copy-Item -LiteralPath $src -Destination (Join-Path $tools $name) -Force
        }
    }
}

$files = [ordered]@{}
Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
    if ($_.Name -eq 'MANIFEST.json' -or $_.Name -eq 'provenance.txt') { return }
    $rel = $_.FullName.Substring($stage.Length).TrimStart('\', '/').Replace('\', '/')
    $files[$rel] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
}
$hover = Join-Path $stage 'src\Public\Get-BobTrayHover.ps1'
if (-not (Test-Path -LiteralPath $hover)) {
    throw 'Stage-BobTrayHotpatchArtifact: missing src/Public/Get-BobTrayHover.ps1'
}
$watch = Join-Path $stage 'tools\Watch-BobTray.ps1'
if (-not (Test-Path -LiteralPath $watch)) {
    throw 'Stage-BobTrayHotpatchArtifact: missing tools/Watch-BobTray.ps1'
}

$sha = ([string]$Commit).Trim()
if (-not $sha) { $sha = ([string]$env:WORKFLOW_COMMIT).Trim() }
if (-not $sha) {
    try { $sha = [string](& git -C $repo rev-parse HEAD 2>$null | Select-Object -First 1) } catch { }
}
$sha = $sha.Trim()
$writer = Join-Path $PSScriptRoot 'Write-BobTrayDeployedIdentity.ps1'
if ($sha -match '^[0-9a-fA-F]{7,40}$' -and (Test-Path -LiteralPath $writer)) {
    & $writer -InstallRoot $stage -Commit $sha -Builder 'Stage-BobTrayHotpatchArtifact.ps1' -Fr '7248' | Out-Null
}

$manPath = Join-Path $stage 'MANIFEST.json'
$man = [ordered]@{
    product = 'bob-tray'
    fr      = '7248'
    files   = $files
}
if (Test-Path -LiteralPath $manPath) {
    try {
        $exist = Get-Content -LiteralPath $manPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($p in @($exist.PSObject.Properties)) {
            if ($p.Name -eq 'files') { continue }
            $man[$p.Name] = $p.Value
        }
    } catch { }
}
$man['files'] = $files
$utf8 = New-Object Text.UTF8Encoding $false
[IO.File]::WriteAllText($manPath, (($man | ConvertTo-Json -Depth 8 -Compress) + [Environment]::NewLine), $utf8)
$toolsMan = Join-Path $stage 'tools\MANIFEST.json'
if (Test-Path -LiteralPath (Split-Path $toolsMan -Parent)) {
    [IO.File]::WriteAllText($toolsMan, (($man | ConvertTo-Json -Depth 8 -Compress) + [Environment]::NewLine), $utf8)
}
Write-Output $stage
