#Requires -Version 5.1
<#
.SYNOPSIS
  Compile the two fast tray dialogs (t828u): bob-about.exe (Acknowledge) and bob-status.exe (Status pools card).
.DESCRIPTION
  C# WinForms compiled with csc.exe of the .NET Framework 4 that ships with every Windows 10/11 (no SDK, no PyInstaller, no extra
  toolchain on the build OR the target machine). The exes are ~30 KB, load only framework assemblies that are already NGEN'd, and start
  in a fraction of a second (a PyInstaller one-file exe unpacks ~10 MB to %TEMP% on EVERY start, and Python+tkinter adds more).
  Sources: <repo>\bob\tray\dialogs\*.cs (flat tree: <root>\dialogs\*.cs). Output: <OutDir>\bob-about.exe, bob-status.exe.
  Called by Pack-BobiverseRelease.ps1 (stage\tools\) and Sync-BobiverseFromRepo.ps1 (compiles into <install>\tools\ when missing or older than the sources).
.OUTPUTS
  The full paths of the exes built.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$SourceDir = ''
)
$ErrorActionPreference = 'Stop'
$cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
if (-not (Test-Path -LiteralPath $cm)) { $cm = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\scripts\Bobiverse-Common.ps1' }
. $cm
if (-not $RepoRoot) { $RepoRoot = Get-BobiverseRepoRoot -ScriptDir $PSScriptRoot }
if (-not $SourceDir) {
    $SourceDir = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\dialogs'   # alias -> bob\tray\dialogs in the split repo
    if (-not (Test-Path -LiteralPath $SourceDir)) { $SourceDir = Join-Path $RepoRoot 'dialogs' }
}
if (-not (Test-Path -LiteralPath (Join-Path $SourceDir 'BobDialogsCommon.cs'))) { throw "missing dialog sources in $SourceDir" }

$csc = $null
foreach ($c in @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'))) {
    if (Test-Path -LiteralPath $c) { $csc = $c; break }
}
if (-not $csc) { throw 'csc.exe (.NET Framework 4) not found' }

# Icon / logo: the systray icon is the exe icon; the ntsa badge is embedded so the About window needs no file read.
$assets = Get-BobiverseRepoPath -Root $RepoRoot -Rel 'third_party\bob-tray\assets'
if (-not (Test-Path -LiteralPath $assets)) { $assets = Join-Path $RepoRoot 'assets' }
$ico = Join-Path $assets 'bob-systray.ico'
$logo = Join-Path $assets 'ntsa-gut-logo.png'
$manifest = Join-Path $SourceDir 'bob-dialogs.manifest'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$built = @()
foreach ($d in @(
        @{ Exe = 'bob-about.exe';  Main = 'BobAbout.cs';  Refs = @('System.ServiceProcess.dll') },
        @{ Exe = 'bob-status.exe'; Main = 'BobStatus.cs'; Refs = @() })) {
    $out = Join-Path $OutDir $d.Exe
    $tmp = $out + '.new'
    $argv = @('/nologo', '/target:winexe', '/optimize+', '/debug-', '/platform:anycpu', "/out:$tmp",
        '/r:System.dll', '/r:System.Core.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll', '/r:System.Web.Extensions.dll')
    foreach ($r in $d.Refs) { $argv += "/r:$r" }
    if (Test-Path -LiteralPath $ico) { $argv += "/win32icon:$ico" }
    if (Test-Path -LiteralPath $manifest) { $argv += "/win32manifest:$manifest" }
    if (Test-Path -LiteralPath $logo) { $argv += "/resource:$logo,ntsa-gut-logo.png" }
    $argv += @((Join-Path $SourceDir 'BobDialogsCommon.cs'), (Join-Path $SourceDir $d.Main))
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $log = & $csc @argv 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $tmp)) {
        ($log | Select-Object -Last 25) | ForEach-Object { Write-Host "  csc: $_" }
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
        throw "csc failed for $($d.Exe) (exit $code)"
    }
    # A running dialog keeps its exe locked: replace via rename so a rebuild never fails on an open window.
    if (Test-Path -LiteralPath $out) {
        try { Remove-Item -LiteralPath $out -Force -ErrorAction Stop }
        catch { try { Move-Item -LiteralPath $out -Destination ($out + '.old') -Force -ErrorAction Stop } catch { } }
    }
    Move-Item -LiteralPath $tmp -Destination $out -Force
    Write-Host ("INFO built {0} ({1:N0} KB)" -f $out, ((Get-Item -LiteralPath $out).Length / 1KB))
    $built += $out
}
$built