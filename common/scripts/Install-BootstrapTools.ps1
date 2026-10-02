#Requires -Version 5.1
<#
.SYNOPSIS
  Install git, gh, Python 3.12+, Node LTS IF MISSING (bobiverse).
.NOTES
  Issue #10: LocalSystem MSI QuietExec often cannot see per-user PATH tools
  (e.g. %LOCALAPPDATA%\Programs\gh). Resolve well-known paths before winget;
  soft-fail optional gh when winget is unavailable so the product MSI does
  not 1603.
#>
[CmdletBinding()]
param(
    [switch]$ForceTools
)

$ErrorActionPreference = 'Stop'

function Add-PathDir([string]$Dir) {
    if (-not $Dir -or -not (Test-Path -LiteralPath $Dir)) { return }
    $parts = $env:Path -split ';' | Where-Object { $_ -and $_.Trim() }
    if ($parts -contains $Dir) { return }
    $env:Path = "$Dir;$env:Path"
}

function Resolve-KnownTool([string]$Name) {
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { return $c.Source }

    $candidates = @()
    switch ($Name.ToLowerInvariant()) {
        'gh' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'GitHub CLI\gh.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\gh\bin\gh.exe'),
                (Join-Path $env:USERPROFILE 'bin\gh\gh.exe'),
                (Join-Path $env:LOCALAPPDATA 'gh-cli\bin\gh.exe')
            )
        }
        'git' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe')
            )
        }
        'python' {
            $candidates = @(
                'C:\Python312\python.exe',
                'C:\Python313\python.exe',
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
                (Join-Path $env:ProgramFiles 'Python312\python.exe')
            )
        }
        'node' {
            $candidates = @(
                (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\node\node.exe')
            )
        }
        'winget' {
            $candidates = @(
                (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'),
                (Join-Path $env:ProgramFiles 'WindowsApps\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\winget.exe')
            )
        }
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            Add-PathDir (Split-Path -Parent $p)
            return $p
        }
    }
    return $null
}

function Test-CmdVersion([string]$Name) {
    return [bool](Resolve-KnownTool $Name)
}

function Install-WingetPackage([string]$Id) {
    $winget = Resolve-KnownTool 'winget'
    if (-not $winget) { return $false }
    & $winget install --id $Id -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Tool {
    param(
        [string]$Label,
        [string]$Cmd,
        [string]$WingetId,
        [scriptblock]$Present,
        [switch]$Optional
    )
    if (-not $ForceTools -and (& $Present)) {
        $resolved = Resolve-KnownTool $Cmd
        if ($resolved) {
            Write-Host "INFO tool-present $Label ($resolved)"
        } else {
            Write-Host "INFO tool-present $Label"
        }
        return
    }
    Write-Host "INFO tool-install $Label via winget $WingetId"
    if (-not (Install-WingetPackage $WingetId)) {
        if ($Optional) {
            Write-Host "WARN tool-missing $Label (winget unavailable or failed) - continuing (issue #10)"
            return
        }
        throw "failed to install $Label (winget $WingetId). Install manually or cache under third_party/bootstrap."
    }
    if (-not (& $Present)) {
        if ($Optional) {
            Write-Host "WARN tool-missing $Label after winget - continuing (issue #10)"
            return
        }
        throw "$Label still missing after winget install"
    }
}

Ensure-Tool 'git' 'git' 'Git.Git' { Test-CmdVersion 'git' }
# gh is used for update-check; soft-fail under LocalSystem quiet MSI (issue #10).
Ensure-Tool 'gh' 'gh' 'GitHub.cli' { Test-CmdVersion 'gh' } -Optional
Ensure-Tool 'python' 'python' 'Python.Python.3.12' {
    $py = Resolve-KnownTool 'python'
    if (-not $py) { return $false }
    $v = & $py -c "import sys; print('%d.%d'%sys.version_info[:2])"
    return ([version]$v -ge [version]'3.12')
}
Ensure-Tool 'node' 'node' 'OpenJS.NodeJS.LTS' { Test-CmdVersion 'node' }

# Runtime deps for irc_agent / seal (issue #3)
$pyPath = Resolve-KnownTool 'python'
if ($pyPath) {
    $here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    . (Join-Path $here 'Bobiverse-Common.ps1')
    try { Install-BobiversePythonDeps -Python $pyPath } catch {
        Write-Host "WARN python deps: $($_.Exception.Message)"
    }
}
Write-Host 'INFO bootstrap-tools done'
