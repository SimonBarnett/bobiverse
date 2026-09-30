#Requires -Version 5.1
# Vendored for bob MSI TipForm tray.
# CAST IRON: product repo ff/Sync/MSI update is owned by ircBob Start-Bob
# (and TipForm Restart -> Restart-BobEar). Tray Start never updates the tree.
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
    summary = 'tray: product update owned by ircBob Start-Bob / Restart-BobEar (no-op)'
}

# Intentionally ignore -Force / Check-BobiverseUpdate / Sync-BobiverseFromRepo / git pull.
$result | ConvertTo-Json -Compress
exit 0
