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
foreach ($leaf in @('MANIFEST.json', 'provenance.txt')) {
    $from = Join-Path $art $leaf
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $root $leaf) -Force
        $tools = Join-Path $root 'tools'
        if (Test-Path -LiteralPath $tools) {
            Copy-Item -LiteralPath $from -Destination (Join-Path $tools $leaf) -Force
        }
    }
}
Write-Output ("INFO tray-hotpatch backup={0} install={1}" -f $BackupDir, $root)
Write-Output $BackupDir
