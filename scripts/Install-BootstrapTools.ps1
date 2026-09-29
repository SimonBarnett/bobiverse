#Requires -Version 5.1
<#
.SYNOPSIS
  Install git, gh, Python 3.12+, Node LTS IF MISSING (bobiverse).
#>
[CmdletBinding()]
param(
    [switch]$ForceTools
)

$ErrorActionPreference = 'Stop'

function Test-CmdVersion([string]$Name) {
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$c
}

function Install-WingetPackage([string]$Id) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { return $false }
    & winget.exe install --id $Id -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Tool {
    param([string]$Label, [string]$Cmd, [string]$WingetId, [scriptblock]$Present)
    if (-not $ForceTools -and (& $Present)) {
        Write-Host "INFO tool-present $Label"
        return
    }
    Write-Host "INFO tool-install $Label via winget $WingetId"
    if (-not (Install-WingetPackage $WingetId)) {
        throw "failed to install $Label (winget $WingetId). Install manually or cache under third_party/bootstrap."
    }
    if (-not (& $Present)) {
        throw "$Label still missing after winget install"
    }
}

Ensure-Tool 'git' 'git' 'Git.Git' { Test-CmdVersion 'git' }
Ensure-Tool 'gh' 'gh' 'GitHub.cli' { Test-CmdVersion 'gh' }
Ensure-Tool 'python' 'python' 'Python.Python.3.12' {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $py) { return $false }
    $v = & python.exe -c "import sys; print('%d.%d'%sys.version_info[:2])"
    return ([version]$v -ge [version]'3.12')
}
Ensure-Tool 'node' 'node' 'OpenJS.NodeJS.LTS' { Test-CmdVersion 'node' }
Write-Host 'INFO bootstrap-tools done'
