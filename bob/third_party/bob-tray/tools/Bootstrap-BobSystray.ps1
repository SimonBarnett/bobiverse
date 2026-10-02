#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap this Windows box (e.g. marchhare) to current Bob Systray on origin/main.

.DESCRIPTION
  Deterministic scripts only (no LLM):
  1. Resolve or clone SimonBarnett/agentic_build
  2. Fetch + fast-forward origin/main (stash dirty tree if needed)
  3. Reinstall ~/.grok/skills from the repo
  4. Install Start Menu + Desktop "Bob Systray" shortcuts (robot .ico)
  5. Optional: ForceNew start the tray (git-update gate runs again; already current)

.EXAMPLE
  # On marchhare (typical tree):
  powershell -NoProfile -ExecutionPolicy Bypass -File D:\AI\agentic_build\tools\Bootstrap-BobSystray.ps1

.EXAMPLE
  # Chicken-egg: no local checkout yet - pipe from GitHub main:
  irm https://raw.githubusercontent.com/SimonBarnett/agentic_build/main/tools/Bootstrap-BobSystray.ps1 | iex

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Bootstrap-BobSystray.ps1 -RepoRoot D:\AI\agentic_build -SkipTrayStart
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$Branch = 'main',
    [string]$RemoteUrl = 'https://github.com/SimonBarnett/agentic_build.git',
    [switch]$SkipTrayStart,
    [switch]$SkipSkills,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$GitExe = 'git'

function Write-Boot([string]$m) {
    Write-Host ('[{0:HH:mm:ss}] {1}' -f [datetime]::Now, $m)
}

function Invoke-BootGit {
    param([string[]]$ArgumentList, [string]$WorkDir)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $GitExe
    $psi.Arguments = ($ArgumentList -join ' ')
    if ($WorkDir) { $psi.WorkingDirectory = $WorkDir }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return [pscustomobject]@{ ExitCode = $p.ExitCode; StdOut = $out; StdErr = $err }
}

function Resolve-AgenticBuildRoot {
    param([string]$Preferred)
    if ($Preferred) {
        $p = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Preferred))
        if (Test-Path -LiteralPath (Join-Path $p '.git')) { return $p }
        if (Test-Path -LiteralPath $p) { return $p }
    }
    if ($PSScriptRoot) {
        $fromScript = Split-Path $PSScriptRoot -Parent
        if (Test-Path -LiteralPath (Join-Path $fromScript 'tools\Watch-BobTray.ps1')) {
            return [IO.Path]::GetFullPath($fromScript)
        }
    }
    foreach ($c in @(
            $env:BOB_FLEET_ROOT,
            'D:\AI\agentic_build',
            'D:\ai\agentic_build',
            'C:\AI\agentic_build',
            'C:\ai\agentic_build',
            'E:\AI\agentic_build',
            'E:\ai\agentic_build',
            (Join-Path $env:USERPROFILE 'AI\agentic_build'),
            (Join-Path $env:USERPROFILE 'ai\agentic_build')
        )) {
        if (-not $c) { continue }
        $p = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($c))
        # Prefer an existing checkout even if Watch-BobTray.ps1 is not yet present (old tip).
        if ((Test-Path -LiteralPath (Join-Path $p '.git')) -or
            (Test-Path -LiteralPath (Join-Path $p 'tools\Watch-BobTray.ps1'))) {
            return $p
        }
    }
    return $null
}

Write-Boot 'Bob Systray bootstrap (deterministic; no LLM)'

$root = Resolve-AgenticBuildRoot -Preferred $RepoRoot
if (-not $root) {
    # Prefer an existing drive root (marchhare often has no D:). Never assume D:\.
    $parent = $null
    foreach ($cand in @(
            'D:\AI', 'D:\ai', 'C:\AI', 'C:\ai', 'E:\AI', 'E:\ai',
            (Join-Path $env:USERPROFILE 'AI'),
            (Join-Path $env:USERPROFILE 'ai')
        )) {
        $driveRoot = [IO.Path]::GetPathRoot($cand)
        if (-not $driveRoot -or -not (Test-Path -LiteralPath $driveRoot)) { continue }
        if (-not (Test-Path -LiteralPath $cand)) {
            New-Item -ItemType Directory -Force -Path $cand | Out-Null
        }
        $parent = $cand
        break
    }
    if (-not $parent) {
        throw 'no writable AI parent folder (tried D:\AI, C:\AI, E:\AI, ~/AI)'
    }
    $root = Join-Path $parent 'agentic_build'
    Write-Boot ("clone {0} -> {1}" -f $RemoteUrl, $root)
    if ($WhatIf) {
        Write-Boot 'WhatIf: would clone'
    }
    else {
        $clone = Invoke-BootGit -ArgumentList @('clone', '--branch', $Branch, $RemoteUrl, $root)
        if ($clone.ExitCode -ne 0 -and -not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
            throw ("git clone failed: {0}" -f $clone.StdErr.Trim())
        }
    }
}

$root = [IO.Path]::GetFullPath($root)
Write-Boot ("repo: {0}" -f $root)
if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
    throw "not a git checkout: $root"
}

# Fetch + ff-only; stash dirty tracked files so bootstrap can land on main tip.
Write-Boot ("fetch origin {0}" -f $Branch)
$fetch = Invoke-BootGit -WorkDir $root -ArgumentList @('fetch', 'origin', $Branch)
if ($fetch.ExitCode -ne 0) { throw ("git fetch failed: {0}" -f $fetch.StdErr.Trim()) }

$status = Invoke-BootGit -WorkDir $root -ArgumentList @('status', '--porcelain')
$dirty = @([string]$status.StdOut -split "`r?`n" | Where-Object { $_ -and $_ -notmatch '^\?\?' })
if ($dirty.Count -gt 0) {
    $stashName = 'bob-systray-bootstrap-{0:yyyyMMdd-HHmmss}' -f [datetime]::UtcNow
    Write-Boot ("dirty tree ({0} tracked) - stash {1}" -f $dirty.Count, $stashName)
    if (-not $WhatIf) {
        $st = Invoke-BootGit -WorkDir $root -ArgumentList @('stash', 'push', '-m', $stashName, '--', '.')
        if ($st.ExitCode -ne 0) { Write-Boot ("stash warning: {0}" -f $st.StdErr.Trim()) }
    }
}

Write-Boot ("checkout {0} + ff-only origin/{0}" -f $Branch)
if (-not $WhatIf) {
    $co = Invoke-BootGit -WorkDir $root -ArgumentList @('checkout', $Branch)
    if ($co.ExitCode -ne 0) { throw ("git checkout failed: {0}" -f $co.StdErr.Trim()) }
    $ff = Invoke-BootGit -WorkDir $root -ArgumentList @('merge', '--ff-only', "origin/$Branch")
    if ($ff.ExitCode -ne 0) {
        # Fall back to reset --hard origin/main after stash (bootstrap target is tip of main).
        Write-Boot 'ff-only failed - reset --hard origin/main (local dirty already stashed if present)'
        $rh = Invoke-BootGit -WorkDir $root -ArgumentList @('reset', '--hard', "origin/$Branch")
        if ($rh.ExitCode -ne 0) { throw ("git reset --hard failed: {0}" -f $rh.StdErr.Trim()) }
    }
}

$sha = (Invoke-BootGit -WorkDir $root -ArgumentList @('rev-parse', '--short', 'HEAD')).StdOut.Trim()
Write-Boot ("HEAD: {0}" -f $sha)

$required = @(
    'tools\Update-BobSystrayFromGit.ps1',
    'tools\Start-BobFleetTray.ps1',
    'tools\Install-BobFleetTrayShortcut.ps1',
    'tools\Show-BobSystrayUpdatingDialog.ps1',
    'assets\bob-systray.ico'
)
foreach ($rel in $required) {
    $p = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $p)) {
        throw "bootstrap target missing $rel - is origin/$Branch new enough? (need #407+)"
    }
}

$ps = (Get-Command powershell.exe).Source

if (-not $SkipSkills) {
    $skills = Join-Path $root 'tools\Reinstall-AgentSkills.ps1'
    if (Test-Path -LiteralPath $skills) {
        Write-Boot 'Reinstall-AgentSkills'
        if (-not $WhatIf) {
            & $ps -NoProfile -ExecutionPolicy Bypass -File $skills -RepoRoot $root | Out-Host
        }
    }
    else {
        Write-Boot 'Reinstall-AgentSkills.ps1 missing - skip skills copy'
    }
}

$short = Join-Path $root 'tools\Install-BobFleetTrayShortcut.ps1'
Write-Boot 'Install Bob Systray Start Menu + Desktop shortcuts'
if (-not $WhatIf) {
    & $ps -NoProfile -ExecutionPolicy Bypass -File $short -RepoRoot $root | Out-Host
}

$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Bob Systray'
Write-Boot ("Start Menu folder: {0}" -f $startMenu)
if (-not (Test-Path -LiteralPath $startMenu)) {
    throw "Start Menu Bob Systray folder missing after install: $startMenu"
}

$trayOk = $false
if (-not $SkipTrayStart) {
    $start = Join-Path $root 'tools\Start-BobFleetTray.ps1'
    Write-Boot 'Start-BobFleetTray -ForceNew (update gate + replace tray)'
    if (-not $WhatIf) {
        # SkipUpdate: we already landed on origin/main tip above.
        & $ps -NoProfile -STA -ExecutionPolicy Bypass -File $start -RepoRoot $root -ForceNew -SkipUpdate | Out-Host
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            throw ("Start-BobFleetTray exit={0}" -f $LASTEXITCODE)
        }
        Start-Sleep -Seconds 1
        $trayOk = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                $_.CommandLine -and (
                    $_.CommandLine -match 'Watch-BobTray\.ps1' -or
                    $_.CommandLine -match '_Watch-BobTray-[^\s"]+\.ps1'
                )
            }).Count -gt 0
        if (-not $trayOk) {
            throw 'Watch-BobTray / seat wrapper not running after Start-BobFleetTray'
        }
    }
}

$report = [pscustomobject]@{
    ok           = $true
    repo         = $root
    sha          = $sha
    branch       = $Branch
    startMenu    = $startMenu
    trayStarted  = $trayOk
    machineHint  = $(if ($env:BOB_MACHINE_ID) { $env:BOB_MACHINE_ID } else { 'set BOB_MACHINE_ID=marchhare if needed' })
}
$report | ConvertTo-Json -Compress
Write-Boot 'bootstrap complete'
exit 0
