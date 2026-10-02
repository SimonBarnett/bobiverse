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
