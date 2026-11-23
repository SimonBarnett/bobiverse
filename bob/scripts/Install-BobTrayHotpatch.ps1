#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7248: install a staged bob-tray CI artifact onto a live bob install (backup + copy).
.DESCRIPTION
  Copies tools\, src\, assets\ from the artifact over <InstallRoot>. Does not restart
  ircBob or Ergo. Restart the tray afterward (Start-BobFleetTray -ForceNew).
  Rollback: copy the backup tree back over InstallRoot.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$ArtifactDir,
    [string]$BackupDir = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstallRoot.TrimEnd('\', '/'))
$art = [IO.Path]::GetFullPath($ArtifactDir.TrimEnd('\', '/'))
if (-not (Test-Path -LiteralPath (Join-Path $art 'tools\Watch-BobTray.ps1'))) {
    throw 'Install-BobTrayHotpatch: artifact missing tools\Watch-BobTray.ps1'
}
if (-not (Test-Path -LiteralPath (Join-Path $art 'src\Public\Get-BobTrayHover.ps1'))) {
    throw 'Install-BobTrayHotpatch: artifact missing src\Public\Get-BobTrayHover.ps1'
}
# FR #9187: refuse applying a dollar-stripped Invoke-BobFleet.ps1 (recurrence of #8877/#9028).
$commonCandidates = @(
    (Join-Path $root 'scripts\Bobiverse-Common.ps1'),
    (Join-Path $root 'common\scripts\Bobiverse-Common.ps1'),
    (Join-Path $PSScriptRoot '..\..\common\scripts\Bobiverse-Common.ps1')
)
$common = $commonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($common) {
    . $common
    if (Get-Command Assert-BobiverseInvokeBobFleetParses -ErrorAction SilentlyContinue) {
        $pre = Assert-BobiverseInvokeBobFleetParses -InstallRoot $art
        if (-not $pre.Ok) {
            throw ("FR #9187 fleet parse gate (artifact): " + $pre.Reason)
        }
    }
}
else {
    $fleetArt = Join-Path $art 'src\Private\Invoke-BobFleet.ps1'
    if (Test-Path -LiteralPath $fleetArt) {
        $fleetText = [IO.File]::ReadAllText($fleetArt)
        if ([regex]::IsMatch($fleetText, 'param\s*\(\s*\[string\]\s*\)')) {
            throw 'FR #9187 fleet parse gate (artifact): nameless param([string]) in Invoke-BobFleet.ps1'
        }
    }
}
if (-not $BackupDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $BackupDir = "$root-backup-tray-$stamp"
}
$BackupDir = [IO.Path]::GetFullPath($BackupDir)
if (-not (Test-Path -LiteralPath $BackupDir)) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}
foreach ($leaf in @('tools', 'src', 'assets')) {
    $from = Join-Path $root $leaf
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $BackupDir $leaf) -Recurse -Force
    }
}
foreach ($leaf in @('MANIFEST.json', 'provenance.txt')) {
    $from = Join-Path $root $leaf
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $BackupDir $leaf) -Force
    }
}
foreach ($leaf in @('tools', 'src', 'assets')) {
    $from = Join-Path $art $leaf
    if (-not (Test-Path -LiteralPath $from)) { continue }
    $to = Join-Path $root $leaf
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
}
# FR #7300: tray identity lives under tools\ only. Never overwrite install-root MANIFEST.json.
foreach ($leaf in @('MANIFEST.json', 'provenance.txt')) {
    $from = Join-Path $art $leaf
    if (Test-Path -LiteralPath $from) {
        $tools = Join-Path $root 'tools'
        New-Item -ItemType Directory -Force -Path $tools | Out-Null
        Copy-Item -LiteralPath $from -Destination (Join-Path $tools $leaf) -Force
    }
}
# FR #9187: post-copy gate so a race/partial copy cannot leave a nameless fleet on the install.
if (Get-Command Assert-BobiverseInvokeBobFleetParses -ErrorAction SilentlyContinue) {
    $post = Assert-BobiverseInvokeBobFleetParses -InstallRoot $root
    if (-not $post.Ok) {
        throw ("FR #9187 fleet parse gate (install): " + $post.Reason)
    }
}
# FR #9199: intentional clickfalse/clicktrue park => strip live bob-tray.exe after hotpatch copy (Watch-only).
$lifeHp = Join-Path $root 'tools\BobTrayLifecycle.ps1'
if (Test-Path -LiteralPath $lifeHp) {
    . $lifeHp
    if (Get-Command Remove-BobTrayLiveExeWhileParked -ErrorAction SilentlyContinue) {
        $parkedHp = Remove-BobTrayLiveExeWhileParked -Root $root
        if ($parkedHp.Parked -and $parkedHp.Removed) {
            Write-Output 'INFO tray-hotpatch FR #9199 removed live bob-tray.exe (intentional park present; Watch-only)'
        }
    }
}
Write-Output ("INFO tray-hotpatch backup={0} install={1}" -f $BackupDir, $root)
Write-Output $BackupDir
